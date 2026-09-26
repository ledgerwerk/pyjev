"""Single- and multi-label classification recipes with explicit escape states."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ..client import AsyncJev, Jev
from ..decisions import BundleDecision, ChoiceDecision, NoulDecision, decision_to_dict
from ..results import BundleResult, ChoiceResult, NoulResult
from ._common import probability, threshold, validate_id, validate_model

OTHER_LABEL = "__other__"
MAX_LABELS = 254


@dataclass(frozen=True, slots=True)
class Label:
    """Stable label ID and optional descriptive text."""

    id: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class ClassifyPlan:
    """Inspect-before-execute plan for one or many classification questions."""

    task: str
    labels: tuple[Label, ...]
    state: dict[str, Any]
    decision: ChoiceDecision | BundleDecision
    mode: Literal["single", "multi"]
    include_other: bool
    min_confidence: float | None
    positive_at: float | None
    negative_below: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "labels": [{"id": label.id, "description": label.description} for label in self.labels],
            "state": self.state,
            "decision": decision_to_dict(self.decision),
            "policy": {
                "mode": self.mode,
                "include_other": self.include_other,
                "min_confidence": self.min_confidence,
                "positive_at": self.positive_at,
                "negative_below": self.negative_below,
            },
        }


@dataclass(frozen=True, slots=True)
class ClassifiedLabel:
    """One label's probability and deterministic interpretation."""

    id: str
    description: str | None
    probability: float
    verdict: Literal["selected", "not_selected", "positive", "negative", "unclear"]
    decision: ChoiceResult | NoulResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "probability": self.probability,
            "verdict": self.verdict,
            "decision": self.decision.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ClassifyResult:
    """Typed classification, including its original Choice or Noul evidence."""

    mode: Literal["single", "multi"]
    labels: tuple[ClassifiedLabel, ...]
    selected_id: str | None
    other_selected: bool
    action: Literal["selected", "other", "classified", "review"]
    decision: ChoiceResult | BundleResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "labels": [label.to_dict() for label in self.labels],
            "selected_id": self.selected_id,
            "other_selected": self.other_selected,
            "action": self.action,
            "decision": self.decision.to_dict(),
        }


def build_classify(
    task: str,
    labels: Sequence[Label | str | tuple[str, str]],
    *,
    mode: Literal["single", "multi"] = "single",
    include_other: bool = False,
    min_confidence: float | None = None,
    positive_at: float | None = None,
    negative_below: float | None = None,
    model: str | None = None,
) -> ClassifyPlan:
    """Build a Choice for single-label or independent Nouls for multi-label work.

    Multi-label classification requires explicit positive and negative policy thresholds;
    the band between them is returned as ``unclear``. ``other`` is a real Choice option
    and is available only for single-label mode.
    """
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a nonempty string")
    if mode not in {"single", "multi"}:
        raise ValueError("mode must be 'single' or 'multi'")
    if not isinstance(include_other, bool):
        raise TypeError("include_other must be a bool")
    validate_model(model)
    normalized = _normalize_labels(labels)
    if not normalized:
        raise ValueError("classify requires at least one label")
    if len(normalized) > MAX_LABELS:
        raise ValueError(f"classify supports at most {MAX_LABELS} labels")
    if mode == "single":
        if len(normalized) < 2 and not include_other:
            raise ValueError("single-label classification requires at least two labels or an explicit other option")
        if min_confidence is not None:
            min_confidence = threshold(min_confidence, "min_confidence")
        if positive_at is not None or negative_below is not None:
            raise ValueError("positive_at and negative_below are only valid in multi-label mode")
        options: dict[str, str | None] = {label.id: label.description for label in normalized}
        if include_other:
            options[OTHER_LABEL] = "The item does not fit any supplied label."
        decision: ChoiceDecision | BundleDecision = ChoiceDecision(
            name="classify",
            question=f"Which supplied label best describes this item? Task: {task}",
            options=options,
            model=model,
        )
        positive_threshold = negative_threshold = None
    else:
        if include_other:
            raise ValueError("include_other is only valid in single-label mode")
        if min_confidence is not None:
            raise ValueError("min_confidence is only valid in single-label mode")
        if positive_at is None or negative_below is None:
            raise ValueError("multi-label mode requires positive_at and negative_below thresholds")
        positive_threshold = threshold(positive_at, "positive_at")
        negative_threshold = threshold(negative_below, "negative_below")
        if negative_threshold >= positive_threshold:
            raise ValueError("negative_below must be less than positive_at")
        questions = {
            f"label_{index:04d}": NoulDecision(
                name=f"label_{index:04d}",
                question=f"Does this item fit the label {label.id!r}? Task: {task}",
                true=label.description or label.id,
                false=f"The item does not fit the label {label.id!r}.",
            )
            for index, label in enumerate(normalized)
        }
        decision = BundleDecision(name="classify", questions=questions, model=model)
    state = {
        "task": task,
        "labels": [{"id": label.id, "description": label.description} for label in normalized],
    }
    return ClassifyPlan(
        task,
        normalized,
        state,
        decision,
        mode,
        include_other,
        min_confidence,
        positive_threshold,
        negative_threshold,
    )


def interpret_classify(plan: ClassifyPlan, result: ChoiceResult | BundleResult) -> ClassifyResult:
    """Interpret synthetic or live primitive results without a client or network."""
    if plan.mode == "single":
        if not isinstance(result, ChoiceResult):
            raise TypeError("single-label classification requires a ChoiceResult")
        known = {label.id for label in plan.labels}
        if not isinstance(result.value, str) or (
            result.value not in known and not (plan.include_other and result.value == OTHER_LABEL)
        ):
            raise ValueError(f"classification returned unknown label {result.value!r}")
        confidence = probability(result.confidence, "classification confidence")
        other_selected = result.value == OTHER_LABEL
        labels = tuple(
            ClassifiedLabel(
                label.id,
                label.description,
                probability(result.probabilities.get(label.id, 0.0), f"probability for label {label.id!r}"),
                "selected" if result.value == label.id else "not_selected",
                result,
            )
            for label in plan.labels
        )
        if plan.min_confidence is None or confidence < plan.min_confidence:
            action: Literal["selected", "other", "classified", "review"] = "review"
        else:
            action = "other" if other_selected else "selected"
        return ClassifyResult(
            "single",
            labels,
            None if other_selected else result.value,
            other_selected,
            action,
            result,
        )

    if not isinstance(result, BundleResult):
        raise TypeError("multi-label classification requires a BundleResult")
    labels: list[ClassifiedLabel] = []
    for index, label in enumerate(plan.labels):
        key = f"label_{index:04d}"
        child = result.answers.get(key)
        if not isinstance(child, NoulResult):
            raise ValueError(f"classification result is missing Noul answer {key!r}")
        value = probability(child.value, f"probability for label {label.id!r}")
        if value >= plan.positive_at:
            verdict: Literal["selected", "not_selected", "positive", "negative", "unclear"] = "positive"
        elif value <= plan.negative_below:
            verdict = "negative"
        else:
            verdict = "unclear"
        labels.append(ClassifiedLabel(label.id, label.description, value, verdict, child))
    has_unclear = any(label.verdict == "unclear" for label in labels)
    return ClassifyResult("multi", tuple(labels), None, False, "review" if has_unclear else "classified", result)


def execute_classify(jev: Jev, plan: ClassifyPlan) -> ClassifyResult:
    result = jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, (ChoiceResult, BundleResult)):
        raise TypeError("Jev.evaluate returned an unexpected result for classify")
    return interpret_classify(plan, result)


async def aexecute_classify(jev: AsyncJev, plan: ClassifyPlan) -> ClassifyResult:
    result = await jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, (ChoiceResult, BundleResult)):
        raise TypeError("AsyncJev.evaluate returned an unexpected result for classify")
    return interpret_classify(plan, result)


def classify(
    jev: Jev,
    task: str,
    labels: Sequence[Label | str | tuple[str, str]],
    *,
    mode: Literal["single", "multi"] = "single",
    include_other: bool = False,
    min_confidence: float | None = None,
    positive_at: float | None = None,
    negative_below: float | None = None,
    model: str | None = None,
) -> ClassifyResult:
    """Build and execute a classification recipe through the supplied sync client."""
    plan = build_classify(
        task,
        labels,
        mode=mode,
        include_other=include_other,
        min_confidence=min_confidence,
        positive_at=positive_at,
        negative_below=negative_below,
        model=model,
    )
    return execute_classify(jev, plan)


async def aclassify(
    jev: AsyncJev,
    task: str,
    labels: Sequence[Label | str | tuple[str, str]],
    *,
    mode: Literal["single", "multi"] = "single",
    include_other: bool = False,
    min_confidence: float | None = None,
    positive_at: float | None = None,
    negative_below: float | None = None,
    model: str | None = None,
) -> ClassifyResult:
    """Native-async counterpart to :func:`classify`."""
    plan = build_classify(
        task,
        labels,
        mode=mode,
        include_other=include_other,
        min_confidence=min_confidence,
        positive_at=positive_at,
        negative_below=negative_below,
        model=model,
    )
    return await aexecute_classify(jev, plan)


def _normalize_labels(labels: Sequence[Label | str | tuple[str, str]]) -> tuple[Label, ...]:
    if not isinstance(labels, (list, tuple)):
        raise TypeError("labels must be a list or tuple to preserve deterministic order")
    normalized: list[Label] = []
    seen: set[str] = set()
    for item in labels:
        if isinstance(item, Label):
            label = item
        elif isinstance(item, str):
            label = Label(item)
        elif isinstance(item, tuple) and len(item) == 2:
            label = Label(item[0], item[1])
        else:
            raise TypeError("labels must contain Label, ID string, or (ID, description) values")
        validate_id(label.id, "label", reserved={OTHER_LABEL})
        if label.id in seen:
            raise ValueError(f"duplicate label ID: {label.id}")
        if label.description is not None and (not isinstance(label.description, str) or not label.description.strip()):
            raise ValueError(f"label {label.id!r} description must be nonempty when supplied")
        seen.add(label.id)
        normalized.append(label)
    return tuple(normalized)
