"""Command-line interface for pyjev."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

import typer
from typesafe_sdk import (
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPITimeoutError,
    TypeSafeAuthenticationError,
    TypeSafeError,
)

from . import __version__
from .client import Jev
from .compile import compile_decision
from .credentials import (
    ENV_NAME,
    CredentialError,
    credential_file_path,
    credential_source,
    delete_api_key,
    set_api_key,
    set_file_api_key,
)
from .decisions import (
    BundleDecision,
    DecisionConfigError,
    NoulDecision,
    decision_to_dict,
    load_config,
    load_decision,
    load_decisions,
)
from .results import BundleResult, ChoiceResult, NoulResult, ScoreResult

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE = 2
EXIT_CONFIDENCE = 3

T = TypeVar("T")
Result = BundleResult | NoulResult | ChoiceResult | ScoreResult

app = typer.Typer(
    no_args_is_help=True,
    help="Reusable, confidence-aware Jev decisions from the shell.",
)
auth_app = typer.Typer(no_args_is_help=True, help="Manage the TypeSafe API key.")
decision_app = typer.Typer(no_args_is_help=True, help="Inspect read-only named decisions.")
app.add_typer(auth_app, name="auth")
app.add_typer(decision_app, name="decision")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the pyjev version and exit.",
    ),
) -> None:
    del version


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise typer.BadParameter(f"Could not read {path}: {exc}") from exc


def _state_value(state: str | None, state_file: Path | None, state_json: bool) -> Any:
    if state is not None and state_file is not None:
        raise typer.BadParameter("Use either --state or --state-file, not both.")

    if state_file is not None:
        text = _read_text(state_file)
    elif state is not None:
        text = state
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        raise typer.BadParameter("Provide --state, --state-file, or pipe state on stdin.")

    if not state_json:
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"State is not valid JSON: {exc}") from exc


def _validate_output_options(*, json_output: bool, value_only: bool) -> None:
    if json_output and value_only:
        raise typer.BadParameter("Use either --json or --value, not both.")


def _validate_min_confidence(value: float | None) -> None:
    if value is not None and not 0 <= value <= 1:
        raise typer.BadParameter("--min-confidence must be between 0 and 1.")


def _print_json(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))


def _emit_result(result: Result, *, json_output: bool, value_only: bool) -> None:
    _validate_output_options(json_output=json_output, value_only=value_only)
    if json_output:
        _print_json(result.to_dict())
        return
    if isinstance(result, BundleResult):
        if value_only:
            raise typer.BadParameter("--value is not valid for bundle decisions.")
        for name, answer in result.answers.items():
            typer.echo(f"[{name}]")
            _emit_result(answer, json_output=False, value_only=False)
        return
    if value_only:
        typer.echo(result.value)
        return

    if isinstance(result, NoulResult):
        typer.echo(f"noul={result.value:.6f}")
    elif isinstance(result, ChoiceResult):
        typer.echo(f"choice={result.value} confidence={result.confidence:.6f}")
    else:
        typer.echo(f"score={result.value:.6f} confidence={result.confidence:.6f}")


def _gate_failed(confidence: float, minimum: float | None) -> bool:
    return minimum is not None and confidence < minimum


def _emit_gate_failure(
    result: ChoiceResult | ScoreResult,
    *,
    minimum: float,
    json_output: bool,
) -> None:
    if json_output:
        _print_json(
            {
                "gate": {
                    "passed": False,
                    "minimum_confidence": minimum,
                    "confidence": result.confidence,
                },
                "result": result.to_dict(),
            }
        )
    else:
        typer.echo(
            f"Confidence {result.confidence:.2f} is below required {minimum:.2f}.",
            err=True,
        )
    raise typer.Exit(code=EXIT_CONFIDENCE)


def _emit_gated_result(
    result: Result,
    *,
    json_output: bool,
    value_only: bool,
    minimum: float | None,
) -> None:
    if isinstance(result, NoulResult):
        _emit_result(result, json_output=json_output, value_only=value_only)
        return
    if minimum is not None and _gate_failed(result.confidence, minimum):
        _emit_gate_failure(result, minimum=minimum, json_output=json_output)
    _emit_result(result, json_output=json_output, value_only=value_only)


def _parse_options(options: list[str]) -> dict[str, str | None]:
    parsed: dict[str, str | None] = {}
    for item in options:
        label, separator, description = item.partition("=")
        label = label.strip()
        if not label:
            raise typer.BadParameter("Choice labels cannot be empty.")
        if label in parsed:
            raise typer.BadParameter(f"Duplicate choice label: {label}")
        parsed[label] = description if separator else None
    if len(parsed) < 2:
        raise typer.BadParameter("Provide at least two --option values.")
    if len(parsed) > 255:
        raise typer.BadParameter("Provide no more than 255 --option values.")
    return parsed


def _parse_decision_error(exc: DecisionConfigError) -> typer.BadParameter:
    return typer.BadParameter(str(exc))


def _run_api(action: Callable[[Jev], T], *, model: str | None = None) -> T:
    try:
        with Jev(model=model) as jev:
            return action(jev)
    except TypeSafeAuthenticationError as exc:
        typer.echo(
            "Error: TypeSafe authentication failed.\nSet TYPESAFE_API_KEY or run `pyjev auth set`.",
            err=True,
        )
        raise typer.Exit(code=EXIT_RUNTIME_ERROR) from exc
    except (TypeSafeAPITimeoutError, TypeSafeAPIConnectionError) as exc:
        typer.echo(f"Error: Could not reach TypeSafe: {exc}", err=True)
        raise typer.Exit(code=EXIT_RUNTIME_ERROR) from exc
    except TypeSafeAPIError as exc:
        typer.echo(f"Error: TypeSafe API request failed: {exc}", err=True)
        raise typer.Exit(code=EXIT_RUNTIME_ERROR) from exc
    except TypeSafeError as exc:
        message = str(exc)
        if "No API key" in message:
            message = "TypeSafe authentication failed. Set TYPESAFE_API_KEY or run `pyjev auth set`."
        typer.echo(f"Error: {message}", err=True)
        raise typer.Exit(code=EXIT_RUNTIME_ERROR) from exc
    except CredentialError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=EXIT_RUNTIME_ERROR) from exc


def _run_noul(
    question: str,
    state: str | None,
    state_file: Path | None,
    state_json: bool,
    true: str | None,
    false: str | None,
    model: str | None,
    json_output: bool,
    value_only: bool,
) -> None:
    _validate_output_options(json_output=json_output, value_only=value_only)
    value = _state_value(state, state_file, state_json)
    result = _run_api(
        lambda jev: jev.noul(question, state=value, true=true, false=false),
        model=model,
    )
    _emit_result(result, json_output=json_output, value_only=value_only)


@app.command("ask")
def ask(
    question: str = typer.Argument(..., help="Yes/no question or statement."),
    state: str | None = typer.Option(None, "--state", "-s", help="State text."),
    state_file: Path | None = typer.Option(None, "--state-file", help="Read state from a file."),
    state_json: bool = typer.Option(False, "--state-json", help="Decode the state as JSON."),
    true: str | None = typer.Option(None, "--true", help="Description of the yes/true outcome."),
    false: str | None = typer.Option(None, "--false", help="Description of the no/false outcome."),
    model: str | None = typer.Option(None, "--model", help="Override the TypeSafe model."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    value_only: bool = typer.Option(False, "--value", help="Emit only the numeric Noul value."),
) -> None:
    _run_noul(question, state, state_file, state_json, true, false, model, json_output, value_only)


@app.command("noul")
def noul(
    question: str = typer.Argument(..., help="Yes/no question or statement."),
    state: str | None = typer.Option(None, "--state", "-s", help="State text."),
    state_file: Path | None = typer.Option(None, "--state-file", help="Read state from a file."),
    state_json: bool = typer.Option(False, "--state-json", help="Decode the state as JSON."),
    true: str | None = typer.Option(None, "--true", help="Description of the yes/true outcome."),
    false: str | None = typer.Option(None, "--false", help="Description of the no/false outcome."),
    model: str | None = typer.Option(None, "--model", help="Override the TypeSafe model."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    value_only: bool = typer.Option(False, "--value", help="Emit only the numeric Noul value."),
) -> None:
    _run_noul(question, state, state_file, state_json, true, false, model, json_output, value_only)


@app.command("choice")
def choice(
    question: str = typer.Argument(..., help="Question to decide."),
    option: list[str] = typer.Option(
        ...,
        "--option",
        "-o",
        help="Choice as LABEL or LABEL=DESCRIPTION. Repeat for each option.",
    ),
    state: str | None = typer.Option(None, "--state", "-s", help="State text."),
    state_file: Path | None = typer.Option(None, "--state-file", help="Read state from a file."),
    state_json: bool = typer.Option(False, "--state-json", help="Decode the state as JSON."),
    model: str | None = typer.Option(None, "--model", help="Override the TypeSafe model."),
    min_confidence: float | None = typer.Option(None, "--min-confidence", help="Exit 3 below this confidence."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    value_only: bool = typer.Option(False, "--value", help="Emit only the selected label."),
) -> None:
    _validate_output_options(json_output=json_output, value_only=value_only)
    _validate_min_confidence(min_confidence)
    value = _state_value(state, state_file, state_json)
    choices = _parse_options(option)
    result = _run_api(lambda jev: jev.choice(question, state=value, choices=choices), model=model)
    _emit_gated_result(
        result,
        json_output=json_output,
        value_only=value_only,
        minimum=min_confidence,
    )


@app.command("score")
def score(
    question: str = typer.Argument(..., help="Question to score."),
    level: list[str] = typer.Option(
        ...,
        "--level",
        "-l",
        help="Ordered score-level description. Repeat from score 0 upward.",
    ),
    state: str | None = typer.Option(None, "--state", "-s", help="State text."),
    state_file: Path | None = typer.Option(None, "--state-file", help="Read state from a file."),
    state_json: bool = typer.Option(False, "--state-json", help="Decode the state as JSON."),
    model: str | None = typer.Option(None, "--model", help="Override the TypeSafe model."),
    min_confidence: float | None = typer.Option(None, "--min-confidence", help="Exit 3 below this confidence."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    value_only: bool = typer.Option(False, "--value", help="Emit only the expected score."),
) -> None:
    _validate_output_options(json_output=json_output, value_only=value_only)
    _validate_min_confidence(min_confidence)
    if not 2 <= len(level) <= 10:
        raise typer.BadParameter("Provide between 2 and 10 --level values.")
    value = _state_value(state, state_file, state_json)
    result = _run_api(lambda jev: jev.score(question, state=value, levels=level), model=model)
    _emit_gated_result(
        result,
        json_output=json_output,
        value_only=value_only,
        minimum=min_confidence,
    )


def _named_decision_result(
    name: str,
    *,
    state: Any,
    config: str | None,
    model: str | None,
) -> Result:
    return _run_api(lambda jev: jev.decide(name, state=state, config=config, model=model), model=model)


@app.command("decide")
def decide(
    name: str = typer.Argument(..., help="Name declared in .pyjev.toml."),
    state: str | None = typer.Option(None, "--state", "-s", help="State text."),
    state_file: Path | None = typer.Option(None, "--state-file", help="Read state from a file."),
    state_json: bool = typer.Option(False, "--state-json", help="Decode the state as JSON."),
    model: str | None = typer.Option(None, "--model", help="Override the decision's model."),
    config: Path | None = typer.Option(None, "--config", help="Path to a .pyjev.toml file."),
    min_confidence: float | None = typer.Option(None, "--min-confidence", help="Exit 3 below this confidence."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    value_only: bool = typer.Option(False, "--value", help="Emit only the selected value."),
) -> None:
    _validate_output_options(json_output=json_output, value_only=value_only)
    _validate_min_confidence(min_confidence)
    try:
        declaration = load_decision(name, config)
    except DecisionConfigError as exc:
        raise _parse_decision_error(exc) from exc
    if isinstance(declaration, (NoulDecision, BundleDecision)) and min_confidence is not None:
        if isinstance(declaration, BundleDecision):
            raise typer.BadParameter("--min-confidence is not valid for bundle decisions.")
        raise typer.BadParameter("--min-confidence is only valid for named Choice and Score decisions.")
    if isinstance(declaration, BundleDecision) and value_only:
        raise typer.BadParameter("--value is not valid for bundle decisions.")
    value = _state_value(state, state_file, state_json)
    result = _named_decision_result(name, state=value, config=str(config) if config else None, model=model)
    _emit_gated_result(
        result,
        json_output=json_output,
        value_only=value_only,
        minimum=min_confidence,
    )


class CredentialStorage(str, Enum):
    auto = "auto"
    keyring = "keyring"
    file = "file"


def _file_warning(path: Path) -> None:
    typer.echo(
        f"Warning: {path} stores the API key as plaintext readable by your user account.",
        err=True,
    )


@auth_app.command("set")
def auth_set(
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="API key. Omit to enter it interactively.",
    ),
    storage: CredentialStorage = typer.Option(
        CredentialStorage.auto,
        "--storage",
        help="Credential storage: auto, keyring, or file.",
    ),
) -> None:
    interactive_key = api_key is None
    if api_key is None:
        api_key = typer.prompt("TypeSafe API key", hide_input=True)

    if storage == CredentialStorage.file:
        path = credential_file_path()
        _file_warning(path)
        try:
            set_file_api_key(api_key)
        except CredentialError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_RUNTIME_ERROR) from exc
        typer.echo(f"Stored TypeSafe API key in {path}.")
        return

    try:
        set_api_key(api_key)
    except CredentialError as exc:
        typer.echo(str(exc), err=True)
        if storage == CredentialStorage.keyring:
            raise typer.Exit(code=EXIT_RUNTIME_ERROR) from exc
        if not interactive_key:
            typer.echo(
                f"Set {ENV_NAME} or use --storage file to store the key in a user-level plaintext file.",
                err=True,
            )
            raise typer.Exit(code=EXIT_RUNTIME_ERROR) from exc

        path = credential_file_path()
        _file_warning(path)
        if not typer.confirm("Store the API key there?", default=False):
            typer.echo(
                f"API key was not stored. Set {ENV_NAME} or configure an OS keyring.",
                err=True,
            )
            raise typer.Exit(code=EXIT_RUNTIME_ERROR) from exc
        try:
            set_file_api_key(api_key)
        except CredentialError as file_exc:
            typer.echo(str(file_exc), err=True)
            raise typer.Exit(code=EXIT_RUNTIME_ERROR) from file_exc
        typer.echo(f"Stored TypeSafe API key in {path}.")
        return
    typer.echo("Stored TypeSafe API key in the OS keyring.")


@auth_app.command("status")
def auth_status() -> None:
    try:
        source = credential_source()
    except CredentialError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=EXIT_RUNTIME_ERROR) from exc
    if source == "environment":
        typer.echo(f"API key available from {ENV_NAME}.")
    elif source == "keyring":
        typer.echo("API key stored in the OS keyring.")
    elif source == "file":
        typer.echo(f"API key stored in {credential_file_path()} (plaintext file).")
    else:
        typer.echo("No API key found.")
        raise typer.Exit(code=EXIT_RUNTIME_ERROR)


@auth_app.command("delete")
def auth_delete() -> None:
    try:
        removed = delete_api_key()
    except CredentialError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=EXIT_RUNTIME_ERROR) from exc
    typer.echo("Deleted stored API key." if removed else "No stored API key found.")
    if os.getenv(ENV_NAME) is not None:
        typer.echo(f"{ENV_NAME} is still set and remains the active credential.")


@decision_app.command("list")
def decision_list(
    config: Path | None = typer.Option(None, "--config", help="Path to a .pyjev.toml file."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    try:
        decisions = load_decisions(config)
    except DecisionConfigError as exc:
        raise _parse_decision_error(exc) from exc
    if json_output:
        _print_json([decision_to_dict(decision) for decision in decisions.values()])
        return
    for decision in decisions.values():
        typer.echo(f"{decision.name}\t{type(decision).__name__.removesuffix('Decision').lower()}")


@decision_app.command("show")
def decision_show(
    name: str = typer.Argument(..., help="Decision name."),
    config: Path | None = typer.Option(None, "--config", help="Path to a .pyjev.toml file."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    try:
        decision = load_decision(name, config)
    except DecisionConfigError as exc:
        raise _parse_decision_error(exc) from exc
    if json_output:
        _print_json(decision_to_dict(decision))
    else:
        typer.echo(f"name={decision.name}")
        typer.echo(f"type={type(decision).__name__.removesuffix('Decision').lower()}")
        if isinstance(decision, BundleDecision):
            typer.echo(f"questions={','.join(decision.questions)}")
        else:
            typer.echo(f"question={decision.question}")


@decision_app.command("validate")
def decision_validate(
    config: Path | None = typer.Option(None, "--config", help="Path to a .pyjev.toml file."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    try:
        loaded = load_config(config)
    except DecisionConfigError as exc:
        raise _parse_decision_error(exc) from exc
    if json_output:
        _print_json(
            {
                "config": str(loaded.path),
                "schema": loaded.schema,
                "decisions": [decision_to_dict(decision) for decision in loaded.decisions.values()],
            }
        )
        return
    typer.echo(f"Valid {loaded.path}: schema {loaded.schema}; {len(loaded.decisions)} decisions")


@decision_app.command("compile")
def decision_compile(
    name: str = typer.Argument(..., help="Name declared in .pyjev.toml."),
    state: str | None = typer.Option(None, "--state", "-s", help="State text."),
    state_file: Path | None = typer.Option(None, "--state-file", help="Read state from a file."),
    state_json: bool = typer.Option(False, "--state-json", help="Decode the state as JSON."),
    model: str | None = typer.Option(None, "--model", help="Override the decision's model."),
    config: Path | None = typer.Option(None, "--config", help="Path to a .pyjev.toml file."),
) -> None:
    value = _state_value(state, state_file, state_json)
    try:
        compiled = compile_decision(name, state=value, config=config, model=model)
    except DecisionConfigError as exc:
        raise _parse_decision_error(exc) from exc
    _print_json(compiled.to_dict())


@app.command("run")
def run(
    request: str = typer.Argument("-", help="JSON request file, or '-' for stdin."),
) -> None:
    text = sys.stdin.read() if request == "-" else _read_text(Path(request))
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Request is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict) or "state" not in payload or "questions" not in payload:
        raise typer.BadParameter("Request must be an object with 'state' and 'questions'.")
    questions = payload["questions"]
    if not isinstance(questions, dict) or not questions:
        raise typer.BadParameter("'questions' must be a non-empty object.")

    result = _run_api(
        lambda jev: jev.run(state=payload["state"], questions=questions),
        model=payload.get("model"),
    )
    _print_json(result)


@app.command("models")
def models(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    available = _run_api(lambda jev: jev.models())
    if json_output:
        _print_json(available)
        return
    for model in available:
        name = model.get("name", "")
        description = model.get("description", "")
        typer.echo(f"{name}\t{description}")


if __name__ == "__main__":
    app()
