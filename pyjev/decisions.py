"""Read-only named decision declarations stored in ``.pyjev.toml``."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found, no-redef]


class DecisionConfigError(ValueError):
    """A named-decision configuration is missing or invalid."""


class DecisionConfigNotFound(DecisionConfigError):
    """No decision configuration could be found."""


@dataclass(frozen=True, slots=True)
class NoulDecision:
    name: str
    question: str
    true: Any | None = None
    false: Any | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class ChoiceDecision:
    name: str
    question: str
    options: dict[str, Any | None]
    model: str | None = None


@dataclass(frozen=True, slots=True)
class ScoreDecision:
    name: str
    question: str
    levels: tuple[Any, ...]
    model: str | None = None


Decision = NoulDecision | ChoiceDecision | ScoreDecision


def find_config(
    config: str | Path | None = None,
    *,
    start: str | Path | None = None,
) -> Path:
    """Resolve an explicit, environment, or nearest-parent config path."""
    if config is not None:
        path = Path(config).expanduser()
        if not path.is_file():
            raise DecisionConfigNotFound(f"Decision config not found: {path}")
        return path.resolve()

    env_config = os.getenv("PYJEV_CONFIG")
    if env_config:
        path = Path(env_config).expanduser()
        if not path.is_file():
            raise DecisionConfigNotFound(f"PYJEV_CONFIG points to missing file: {path}")
        return path.resolve()

    location = Path(start).expanduser() if start is not None else Path.cwd()
    if location.is_file():
        location = location.parent
    location = location.resolve()
    for directory in (location, *location.parents):
        candidate = directory / ".pyjev.toml"
        if candidate.is_file():
            return candidate
    raise DecisionConfigNotFound(
        f"Could not find .pyjev.toml from {location}; pass config=... or use the CLI --config PATH option."
    )


def _error(path: Path, name: str | None, field: str, message: str) -> DecisionConfigError:
    target = f"decision {name!r}" if name is not None else "configuration"
    return DecisionConfigError(f"{path}: {target}: {field}: {message}")


def _json_compatible(value: Any) -> bool:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


def _require_table(value: Any, path: Path, name: str | None, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(path, name, field, "expected a TOML table")
    return value


def _question(table: dict[str, Any], path: Path, name: str) -> str:
    value = table.get("question")
    if not isinstance(value, str) or not value.strip():
        raise _error(path, name, "question", "must be a nonempty string")
    return value


def _model(table: dict[str, Any], path: Path, name: str) -> str | None:
    value = table.get("model")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _error(path, name, "model", "must be a nonempty string")
    return value


def _check_fields(table: dict[str, Any], allowed: set[str], path: Path, name: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise _error(path, name, unknown[0], "unknown field")


def _parse_decision(name: str, raw: Any, path: Path) -> Decision:
    if not isinstance(name, str) or not name.strip():
        raise _error(path, name, "name", "must be a nonempty string")
    table = _require_table(raw, path, name, "decision")
    kind = table.get("type")
    if kind not in {"noul", "choice", "score"}:
        raise _error(path, name, "type", "must be exactly noul, choice, or score")
    question = _question(table, path, name)
    model = _model(table, path, name)

    if kind == "noul":
        _check_fields(table, {"type", "question", "true", "false", "model"}, path, name)
        for field in ("true", "false"):
            if field in table and not _json_compatible(table[field]):
                raise _error(path, name, field, "must be JSON-compatible")
        return NoulDecision(name=name, question=question, true=table.get("true"), false=table.get("false"), model=model)

    if kind == "choice":
        _check_fields(table, {"type", "question", "options", "model"}, path, name)
        options = table.get("options")
        if not isinstance(options, dict):
            raise _error(path, name, "options", "must be a TOML table")
        if not 2 <= len(options) <= 255:
            raise _error(path, name, "options", "must contain between 2 and 255 options")
        parsed_options: dict[str, Any | None] = {}
        for label, description in options.items():
            if not isinstance(label, str) or not label.strip():
                raise _error(path, name, "options", "labels must be nonempty strings")
            if label in parsed_options:
                raise _error(path, name, "options", f"duplicate label {label!r}")
            if not _json_compatible(description):
                raise _error(path, name, f"options.{label}", "must be JSON-compatible")
            parsed_options[label] = description
        return ChoiceDecision(name=name, question=question, options=parsed_options, model=model)

    _check_fields(table, {"type", "question", "levels", "model"}, path, name)
    levels = table.get("levels")
    if not isinstance(levels, list):
        raise _error(path, name, "levels", "must be an array")
    if not 2 <= len(levels) <= 10:
        raise _error(path, name, "levels", "must contain between 2 and 10 levels")
    if not all(_json_compatible(level) for level in levels):
        raise _error(path, name, "levels", "must contain only JSON-compatible values")
    return ScoreDecision(name=name, question=question, levels=tuple(levels), model=model)


def load_decisions(config: str | Path | None = None) -> dict[str, Decision]:
    """Load and strictly validate every named decision in a config file."""
    path = find_config(config)
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except OSError as exc:
        raise DecisionConfigError(f"Could not read decision config {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise DecisionConfigError(f"{path}: invalid TOML: {exc}") from exc

    raw_decisions = document.get("decision")
    if not isinstance(raw_decisions, dict):
        raise DecisionConfigError(f"{path}: decision: expected a TOML table")
    decisions: dict[str, Decision] = {}
    for name, raw in raw_decisions.items():
        if name in decisions:
            raise _error(path, name, "name", "duplicate decision name")
        decisions[name] = _parse_decision(name, raw, path)
    return decisions


def load_decision(name: str, config: str | Path | None = None) -> Decision:
    """Load one named decision after validating the complete configuration."""
    if not isinstance(name, str) or not name.strip():
        raise DecisionConfigError("Decision name must be a nonempty string.")
    decisions = load_decisions(config)
    try:
        return decisions[name]
    except KeyError as exc:
        path = find_config(config)
        raise DecisionConfigError(f"{path}: decision {name!r}: not found") from exc


def decision_to_dict(decision: Decision) -> dict[str, Any]:
    """Return a JSON-serializable representation for CLI output."""
    if isinstance(decision, NoulDecision):
        result: dict[str, Any] = {
            "name": decision.name,
            "type": "noul",
            "question": decision.question,
        }
        if decision.true is not None:
            result["true"] = decision.true
        if decision.false is not None:
            result["false"] = decision.false
    elif isinstance(decision, ChoiceDecision):
        result = {
            "name": decision.name,
            "type": "choice",
            "question": decision.question,
            "options": decision.options,
        }
    else:
        result = {
            "name": decision.name,
            "type": "score",
            "question": decision.question,
            "levels": list(decision.levels),
        }
    if decision.model is not None:
        result["model"] = decision.model
    return result
