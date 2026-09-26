"""Deterministic literal candidate discovery with semantic Choice selection."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ..client import AsyncJev, Jev
from ..decisions import BundleDecision, ChoiceDecision, decision_to_dict
from ..results import BundleResult, ChoiceResult

Normalizer = Callable[[str], Any]
CandidateExtractor = Callable[[str], Iterable[str]]
_FIELD_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}\Z")
_NONE_OPTION = "__none__"
MAX_FIELD_CANDIDATES = 254
DEFAULT_MAX_CANDIDATES = 64


def _identity(value: str) -> str:
    return value


@dataclass(frozen=True, slots=True)
class Field:
    """A named field with deterministic candidate discovery and normalization."""

    name: str
    description: str
    extractor: CandidateExtractor
    normalizer: Normalizer = _identity
    max_candidates: int = DEFAULT_MAX_CANDIDATES


@dataclass(frozen=True, slots=True)
class FieldPlan:
    """The source field and its stable, deduplicated literal candidate options."""

    field: Field
    candidate_ids: tuple[str, ...]
    candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExtractPlan:
    """Credential-free request preview and policy for deterministic extraction."""

    document: str
    fields: tuple[FieldPlan, ...]
    state: dict[str, Any]
    decision: BundleDecision | None
    min_confidence: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "decision": decision_to_dict(self.decision) if self.decision is not None else None,
            "fields": [
                {
                    "name": item.field.name,
                    "description": item.field.description,
                    "candidate_ids": list(item.candidate_ids),
                    "candidates": list(item.candidates),
                    "max_candidates": item.field.max_candidates,
                }
                for item in self.fields
            ],
            "policy": {"min_confidence": self.min_confidence},
        }


@dataclass(frozen=True, slots=True)
class FieldResult:
    """Exact selected source literal, normalized value, local action, and evidence."""

    name: str
    action: Literal["auto", "review", "none", "no_candidates"]
    source_value: str | None
    normalized_value: Any | None
    decision: ChoiceResult | None
    normalization_error: str | None = None

    @property
    def normalized(self) -> Any | None:
        """Short alias for the deterministic normalized value."""
        return self.normalized_value

    def to_dict(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "action": self.action,
            "source_value": self.source_value,
            "normalized_value": self.normalized_value,
            "normalization_error": self.normalization_error,
        }
        if self.decision is not None:
            result["decision"] = self.decision.to_dict()
        return result


@dataclass(frozen=True, slots=True)
class ExtractResult:
    """Per-field extraction outcomes and the shared underlying bundle evidence."""

    fields: dict[str, FieldResult]
    decision: BundleResult | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fields": {name: result.to_dict() for name, result in self.fields.items()},
            "decision": self.decision.to_dict() if self.decision is not None else None,
        }


def regex_field(
    name: str,
    pattern: str,
    *,
    description: str,
    group: int | str = 0,
    flags: int = 0,
    normalizer: Normalizer = _identity,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> Field:
    """Create a field whose candidates are regex matches in source order.

    The regex finds literal candidates; Jev may select only one of those values or
    ``none``. ``group`` may be a numbered or named capture. Candidate matches are
    deduplicated later while preserving their first source occurrence.
    """
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("regex pattern must be a nonempty string")
    compiled = re.compile(pattern, flags)
    if isinstance(group, bool) or not isinstance(group, (int, str)):
        raise ValueError("regex group must be an integer or named group")
    if isinstance(group, int) and not 0 <= group <= compiled.groups:
        raise ValueError("regex group number does not exist")
    if isinstance(group, str) and group not in compiled.groupindex:
        raise ValueError(f"regex group {group!r} does not exist")

    def candidates(document: str) -> list[str]:
        values: list[str] = []
        for match in compiled.finditer(document):
            value = match.group(group)
            if value:
                values.append(value)
        return values

    return Field(name, description, candidates, normalizer, max_candidates)


def build_extract(
    document: str,
    fields: Sequence[Field],
    *,
    min_confidence: float | None = None,
    model: str | None = None,
) -> ExtractPlan:
    """Discover and deduplicate literal candidates without credentials or network I/O."""
    if not isinstance(document, str):
        raise TypeError("document must be text")
    if not isinstance(fields, (list, tuple)) or not fields:
        raise ValueError("fields must be a nonempty list or tuple")
    if min_confidence is not None:
        min_confidence = _threshold(min_confidence)
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError("model must be a nonempty string or None")

    plans: list[FieldPlan] = []
    questions: dict[str, ChoiceDecision] = {}
    state_fields: dict[str, Any] = {}
    seen_names: set[str] = set()
    for field in fields:
        if not isinstance(field, Field):
            raise TypeError("fields must contain Field objects")
        if not isinstance(field.name, str) or _FIELD_NAME.fullmatch(field.name) is None:
            raise ValueError("field names must match [A-Za-z][A-Za-z0-9_.:-]{0,63}")
        if field.name in seen_names:
            raise ValueError(f"duplicate field name: {field.name}")
        seen_names.add(field.name)
        if not isinstance(field.description, str) or not field.description.strip():
            raise ValueError(f"field {field.name!r} description must be nonempty")
        if not callable(field.extractor) or not callable(field.normalizer):
            raise TypeError(f"field {field.name!r} extractor and normalizer must be callable")
        if (
            isinstance(field.max_candidates, bool)
            or not isinstance(field.max_candidates, int)
            or not 1 <= field.max_candidates <= MAX_FIELD_CANDIDATES
        ):
            raise ValueError(f"field {field.name!r} max_candidates must be between 1 and {MAX_FIELD_CANDIDATES}")

        extracted = field.extractor(document)
        if isinstance(extracted, (str, bytes)):
            raise TypeError(f"field {field.name!r} extractor must return an iterable of strings, not text")
        unique: list[str] = []
        seen_values: set[str] = set()
        for value in extracted:
            if not isinstance(value, str):
                raise TypeError(f"field {field.name!r} candidates must be strings")
            if value and value not in seen_values:
                seen_values.add(value)
                unique.append(value)
        if len(unique) > field.max_candidates:
            raise ValueError(
                f"field {field.name!r} found {len(unique)} candidates, over max_candidates={field.max_candidates}"
            )

        candidate_ids = tuple(f"candidate-{index:04d}" for index in range(len(unique)))
        field_plan = FieldPlan(field, candidate_ids, tuple(unique))
        plans.append(field_plan)
        if not unique:
            continue

        options: dict[str, str | None] = dict(zip(candidate_ids, unique, strict=True))
        options[_NONE_OPTION] = f"None of these literals is {field.description}."
        state_fields[field.name] = {
            "description": field.description,
            "candidates": [
                {"id": candidate_id, "value": value} for candidate_id, value in zip(candidate_ids, unique, strict=True)
            ],
        }
        questions[field.name] = ChoiceDecision(
            name=field.name,
            question=(
                f"Which exact candidate literal, if any, is {field.description}? "
                f"Choose a supplied candidate ID or {_NONE_OPTION!r}. Never invent a value."
            ),
            options=options,
        )

    state = {"document": document, "fields": state_fields}
    decision = BundleDecision(name="extract", questions=questions, model=model) if questions else None
    return ExtractPlan(document, tuple(plans), state, decision, min_confidence)


def interpret_extract(plan: ExtractPlan, decision: BundleResult) -> ExtractResult:
    """Interpret an extraction bundle; normalizers are deterministic local functions."""
    if not isinstance(decision, BundleResult):
        raise TypeError("extraction interpretation requires a BundleResult")
    outcomes: dict[str, FieldResult] = {}
    for field_plan in plan.fields:
        field = field_plan.field
        if not field_plan.candidates:
            outcomes[field.name] = FieldResult(field.name, "no_candidates", None, None, None)
            continue
        answer = decision.answers.get(field.name)
        if not isinstance(answer, ChoiceResult):
            raise ValueError(f"extraction result is missing Choice answer for field {field.name!r}")
        if (
            isinstance(answer.confidence, bool)
            or not isinstance(answer.confidence, (int, float))
            or not math.isfinite(answer.confidence)
            or not 0 <= answer.confidence <= 1
        ):
            raise ValueError(f"invalid confidence for field {field.name!r}")
        candidate_by_id = dict(zip(field_plan.candidate_ids, field_plan.candidates, strict=True))
        if answer.value == _NONE_OPTION:
            action: Literal["auto", "review", "none", "no_candidates"] = "none"
            if plan.min_confidence is not None and answer.confidence < plan.min_confidence:
                action = "review"
            outcomes[field.name] = FieldResult(field.name, action, None, None, answer)
            continue
        if answer.value not in candidate_by_id:
            raise ValueError(f"field {field.name!r} selected an unknown candidate ID")

        source_value = candidate_by_id[answer.value]
        try:
            normalized_value = field.normalizer(source_value)
            json.dumps(normalized_value, allow_nan=False)
        except Exception as exc:
            error = f"Normalizer raised {type(exc).__name__}; normalized value is unavailable."
            outcomes[field.name] = FieldResult(field.name, "review", source_value, None, answer, error)
            continue
        action = "auto" if plan.min_confidence is not None and answer.confidence >= plan.min_confidence else "review"
        outcomes[field.name] = FieldResult(field.name, action, source_value, normalized_value, answer)
    return ExtractResult(outcomes, decision)


def execute_extract(jev: Jev, plan: ExtractPlan) -> ExtractResult:
    """Execute an extraction plan or return locally discovered empty fields without I/O."""
    if plan.decision is None:
        return _empty_result(plan)
    result = jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, BundleResult):
        raise TypeError("Jev.evaluate returned a non-bundle result for an extraction plan")
    return interpret_extract(plan, result)


async def aexecute_extract(jev: AsyncJev, plan: ExtractPlan) -> ExtractResult:
    """Native async counterpart to :func:`execute_extract`."""
    if plan.decision is None:
        return _empty_result(plan)
    result = await jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, BundleResult):
        raise TypeError("AsyncJev.evaluate returned a non-bundle result for an extraction plan")
    return interpret_extract(plan, result)


def extract(
    jev: Jev,
    document: str,
    fields: Sequence[Field],
    *,
    min_confidence: float | None = None,
    model: str | None = None,
) -> ExtractResult:
    """Build and execute deterministic candidate extraction with local normalization."""
    plan = build_extract(document, fields, min_confidence=min_confidence, model=model)
    return execute_extract(jev, plan)


async def aextract(
    jev: AsyncJev,
    document: str,
    fields: Sequence[Field],
    *,
    min_confidence: float | None = None,
    model: str | None = None,
) -> ExtractResult:
    """Async build and execution counterpart to :func:`extract`."""
    plan = build_extract(document, fields, min_confidence=min_confidence, model=model)
    return await aexecute_extract(jev, plan)


def _empty_result(plan: ExtractPlan) -> ExtractResult:
    return ExtractResult(
        fields={
            field_plan.field.name: FieldResult(field_plan.field.name, "no_candidates", None, None, None)
            for field_plan in plan.fields
        },
        decision=None,
    )


def _threshold(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("min_confidence must be a finite number between 0 and 1")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 <= normalized <= 1:
        raise ValueError("min_confidence must be a finite number between 0 and 1")
    return normalized
