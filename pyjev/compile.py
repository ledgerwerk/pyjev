"""Offline compilation of named pyjev decisions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from typesafe_sdk import Choice, Noul, NoulCriteria, Question, Score

from .decisions import (
    BundleDecision,
    ChoiceDecision,
    Decision,
    NoulDecision,
    ScoreDecision,
    decision_spec_fingerprint,
    load_decision,
)


def validate_choice_criteria(choices: Mapping[str, Any | None] | Sequence[str]) -> dict[str, Any | None]:
    """Normalize and validate Choice criteria before an SDK request."""
    if isinstance(choices, Mapping):
        criteria = dict(choices)
    else:
        labels = list(choices)
        if len(labels) != len(set(labels)):
            raise ValueError("choice sequence contains duplicate labels")
        criteria = {name: None for name in labels}
    if not 2 <= len(criteria) <= 255:
        raise ValueError("choice requires between 2 and 255 options")
    for label in criteria:
        if not isinstance(label, str) or not label.strip():
            raise ValueError("choice labels must be nonempty strings")
    return criteria


def validate_score_levels(levels: Sequence[Any]) -> list[Any]:
    """Normalize and validate ordered Score levels before an SDK request."""
    values = list(levels)
    if not 2 <= len(values) <= 10:
        raise ValueError("score requires between 2 and 10 levels")
    return values


def build_noul(question: Any, *, true: Any | None = None, false: Any | None = None) -> Noul:
    """Build the official SDK Noul question used by live and compiled requests."""
    criteria: NoulCriteria | None = None
    if true is not None or false is not None:
        criteria = {"true": true, "false": false}
    return Noul(instructions=question, criteria=criteria)


def build_choice(question: Any, choices: Mapping[str, Any | None] | Sequence[str]) -> Choice:
    """Build the official SDK Choice question used by live and compiled requests."""
    return Choice(instructions=question, criteria=validate_choice_criteria(choices))


def build_score(question: Any, levels: Sequence[Any]) -> Score:
    """Build the official SDK Score question used by live and compiled requests."""
    return Score(instructions=question, criteria=validate_score_levels(levels))


def build_question(decision: Decision) -> Question:
    """Build the SDK question for a validated primitive decision declaration."""
    if isinstance(decision, NoulDecision):
        return build_noul(decision.question, true=decision.true, false=decision.false)
    if isinstance(decision, ChoiceDecision):
        return build_choice(decision.question, decision.options)
    if isinstance(decision, ScoreDecision):
        return build_score(decision.question, decision.levels)
    raise TypeError(f"Unsupported decision type: {type(decision).__name__}")


def build_decision_questions(decision: Decision) -> dict[str, Question]:
    """Build all SDK questions for a primitive or bundle declaration."""
    if isinstance(decision, BundleDecision):
        return {name: build_question(child) for name, child in decision.questions.items()}
    return {"answer": build_question(decision)}


def _config_identifier(path: Path) -> str:
    """Return a stable, non-absolute identifier for compiled output."""
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.name


@dataclass(frozen=True, slots=True)
class CompiledDecision:
    """A credential-free, normalized request preview for a named decision."""

    name: str
    kind: str
    state: Any
    questions: dict[str, Question]
    model: str | None
    config_path: Path
    schema: int
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        """Return the stable, deterministic JSON-compatible preview contract."""
        return {
            "schema": self.schema,
            "decision": {
                "name": self.name,
                "type": self.kind,
                "config": _config_identifier(self.config_path),
                "fingerprint": self.fingerprint,
            },
            "request": {
                "state": self.state,
                "questions": {name: _question_to_dict(question) for name, question in self.questions.items()},
                "model": self.model,
            },
        }


def _question_to_dict(question: Question) -> dict[str, Any]:
    """Serialize either an SDK question model or its raw dictionary form."""
    if isinstance(question, (Noul, Choice, Score)):
        return question.model_dump(mode="json")
    return dict(question)


def validate_runtime_decision(decision: Decision) -> Decision:
    """Validate an in-memory decision without creating a client or making a request.

    Dynamic declarations share the same question builders and basic invariants as
    named contracts, but bundle children cannot define their own model override.
    """
    if isinstance(decision, BundleDecision):
        if not isinstance(decision.name, str) or not decision.name.strip():
            raise ValueError("bundle decision name must be a nonempty string")
        if not isinstance(decision.questions, Mapping) or not decision.questions:
            raise ValueError("bundle decision requires at least one question")
        if decision.model is not None and (not isinstance(decision.model, str) or not decision.model.strip()):
            raise ValueError("decision model must be a nonempty string or None")
        for name, child in decision.questions.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("bundle question names must be nonempty strings")
            if not isinstance(child, (NoulDecision, ChoiceDecision, ScoreDecision)):
                raise TypeError(f"unsupported decision type for bundle question {name!r}")
            if child.name != name:
                raise ValueError(f"bundle question key {name!r} must match child decision name {child.name!r}")
            if child.model is not None:
                raise ValueError("child model overrides are not allowed in a bundle")
            _validate_runtime_primitive(child)
        return decision
    if not isinstance(decision, (NoulDecision, ChoiceDecision, ScoreDecision)):
        raise TypeError(f"unsupported decision type: {type(decision).__name__}")
    _validate_runtime_primitive(decision)
    return decision


def _validate_runtime_primitive(decision: NoulDecision | ChoiceDecision | ScoreDecision) -> None:
    if not isinstance(decision.name, str) or not decision.name.strip():
        raise ValueError("decision name must be a nonempty string")
    if not isinstance(decision.question, str) or not decision.question.strip():
        raise ValueError("decision question must be a nonempty string")
    if decision.model is not None and (not isinstance(decision.model, str) or not decision.model.strip()):
        raise ValueError("decision model must be a nonempty string or None")
    # Constructing the SDK question performs the same local type/cardinality checks
    # as named decisions and never resolves credentials or performs network I/O.
    build_question(decision)


def compile_decision(
    name: str,
    *,
    state: Any,
    config: str | Path | None = None,
    model: str | None = None,
) -> CompiledDecision:
    """Compile a named primitive decision without constructing a client or calling the API.

    Parameters
    ----------
    name:
        Name declared in `.pyjev.toml`.
    state:
        State that would be sent to Jev.
    config:
        Optional explicit decision configuration path.
    model:
        Optional model override. It wins over the declaration's model.

    Returns
    -------
    CompiledDecision
        Immutable normalized request preview.
    """
    decision = load_decision(name, config)
    effective_model = model if model is not None else decision.model
    kind = type(decision).__name__.removesuffix("Decision").lower()
    # load_decision validates the complete file; compile deliberately never creates Jev.
    path = Path(config).expanduser().resolve() if config is not None else None
    if path is None:
        from .decisions import find_config

        path = find_config()
    return CompiledDecision(
        name=name,
        kind=kind,
        state=state,
        questions=build_decision_questions(decision),
        model=effective_model,
        config_path=path,
        schema=1,
        fingerprint=decision_spec_fingerprint(decision),
    )
