"""Command-line interface for pyjev."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

from . import __version__
from .client import Jev
from .credentials import CredentialError, credential_source, delete_api_key, set_api_key
from .results import ChoiceResult, NoulResult, ScoreResult

app = typer.Typer(
    no_args_is_help=True,
    help="Reusable, confidence-aware Jev decisions from the shell.",
)
auth_app = typer.Typer(no_args_is_help=True, help="Manage the TypeSafe API key.")
app.add_typer(auth_app, name="auth")


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


def _print_json(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))


def _emit_result(
    result: NoulResult | ChoiceResult | ScoreResult,
    *,
    json_output: bool,
    value_only: bool,
) -> None:
    if json_output and value_only:
        raise typer.BadParameter("Use either --json or --value, not both.")
    if json_output:
        _print_json(result.to_dict())
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


def _confidence_gate(confidence: float, minimum: float | None) -> None:
    if minimum is None:
        return
    if not 0 <= minimum <= 1:
        raise typer.BadParameter("--min-confidence must be between 0 and 1.")
    if confidence < minimum:
        raise typer.Exit(code=2)


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
    return parsed


def _client(model: str | None) -> Jev:
    return Jev(model=model)


@auth_app.command("set")
def auth_set(
    api_key: str = typer.Option(
        ...,
        "--api-key",
        prompt="TypeSafe API key",
        hide_input=True,
        help="API key to store in the OS keyring.",
    ),
) -> None:
    try:
        set_api_key(api_key)
    except CredentialError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("Stored TypeSafe API key in the OS keyring.")


@auth_app.command("status")
def auth_status() -> None:
    source = credential_source()
    if source == "environment":
        typer.echo("API key available from TYPESAFE_API_KEY.")
    elif source == "keyring":
        typer.echo("API key stored in the OS keyring.")
    else:
        typer.echo("No API key found.")
        raise typer.Exit(code=1)


@auth_app.command("delete")
def auth_delete() -> None:
    try:
        removed = delete_api_key()
    except CredentialError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("Deleted stored API key." if removed else "No stored API key found.")


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
    value = _state_value(state, state_file, state_json)
    with _client(model) as jev:
        result = jev.noul(question, state=value, true=true, false=false)
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
    min_confidence: float | None = typer.Option(None, "--min-confidence", help="Exit 2 below this confidence."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    value_only: bool = typer.Option(False, "--value", help="Emit only the selected label."),
) -> None:
    value = _state_value(state, state_file, state_json)
    choices = _parse_options(option)
    with _client(model) as jev:
        result = jev.choice(question, state=value, choices=choices)
    _emit_result(result, json_output=json_output, value_only=value_only)
    _confidence_gate(result.confidence, min_confidence)


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
    min_confidence: float | None = typer.Option(None, "--min-confidence", help="Exit 2 below this confidence."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    value_only: bool = typer.Option(False, "--value", help="Emit only the expected score."),
) -> None:
    if not level:
        raise typer.BadParameter("Provide at least one --level.")
    value = _state_value(state, state_file, state_json)
    with _client(model) as jev:
        result = jev.score(question, state=value, levels=level)
    _emit_result(result, json_output=json_output, value_only=value_only)
    _confidence_gate(result.confidence, min_confidence)


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

    with _client(payload.get("model")) as jev:
        result = jev.run(state=payload["state"], questions=questions)
    _print_json(result)


@app.command("models")
def models(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    with _client(None) as jev:
        available = jev.models()
    if json_output:
        _print_json(available)
        return
    for model in available:
        name = model.get("name", "")
        description = model.get("description", "")
        typer.echo(f"{name}\t{description}")


if __name__ == "__main__":
    app()
