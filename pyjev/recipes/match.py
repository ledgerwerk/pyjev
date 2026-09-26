"""Entity matching with an explicit ``unclear`` semantic outcome."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..client import AsyncJev, Jev
from ..decisions import ChoiceDecision, decision_to_dict
from ..results import ChoiceResult
from ._common import probability, threshold, validate_model

MATCH_OPTIONS = {
    "same": "Both records refer to the same entity.",
    "unclear": "The supplied information is insufficient to decide confidently.",
    "different": "The records refer to different entities.",
}


@dataclass(frozen=True, slots=True)
class MatchPlan:
    """Credential-free, inspectable pairwise match request and optional policy."""

    left: str
    right: str
    task: str
    state: dict[str, Any]
    decision: ChoiceDecision
    min_confidence: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "right": self.right,
            "task": self.task,
            "state": self.state,
            "decision": decision_to_dict(self.decision),
            "policy": {"min_confidence": self.min_confidence},
        }


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Categorical relation, deterministic caller action, and full Choice evidence."""

    verdict: Literal["same", "unclear", "different"]
    confidence: float
    probabilities: dict[str, float]
    action: Literal["auto_match", "auto_different", "review"]
    decision: ChoiceResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "probabilities": dict(self.probabilities),
            "action": self.action,
            "decision": self.decision.to_dict(),
        }


def build_match(
    left: str,
    right: str,
    *,
    task: str = "Determine whether the two records refer to the same entity.",
    min_confidence: float | None = None,
    model: str | None = None,
) -> MatchPlan:
    """Build a three-way Choice request; numeric Score values are not used as verdicts."""
    for label, value in (("left", left), ("right", right), ("task", task)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be a nonempty string")
    validate_model(model)
    if min_confidence is not None:
        min_confidence = threshold(min_confidence, "min_confidence")
    decision = ChoiceDecision(
        name="match",
        question=task,
        options=dict(MATCH_OPTIONS),
        model=model,
    )
    state = {"left": left, "right": right, "task": task}
    return MatchPlan(left, right, task, state, decision, min_confidence)


def interpret_match(plan: MatchPlan, result: ChoiceResult) -> MatchResult:
    """Interpret a synthetic or live match result without transport or side effects."""
    if not isinstance(result, ChoiceResult):
        raise TypeError("match interpretation requires a ChoiceResult")
    if not isinstance(result.value, str) or result.value not in MATCH_OPTIONS:
        raise ValueError(f"match returned unknown verdict {result.value!r}")
    confidence = probability(result.confidence, "match confidence")
    probabilities = {
        verdict: probability(result.probabilities.get(verdict, 0.0), f"probability for {verdict!r}")
        for verdict in MATCH_OPTIONS
    }
    if plan.min_confidence is None or confidence < plan.min_confidence or result.value == "unclear":
        action: Literal["auto_match", "auto_different", "review"] = "review"
    elif result.value == "same":
        action = "auto_match"
    else:
        action = "auto_different"
    return MatchResult(result.value, confidence, probabilities, action, result)


def execute_match(jev: Jev, plan: MatchPlan) -> MatchResult:
    result = jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, ChoiceResult):
        raise TypeError("Jev.evaluate returned an unexpected result for match")
    return interpret_match(plan, result)


async def aexecute_match(jev: AsyncJev, plan: MatchPlan) -> MatchResult:
    result = await jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, ChoiceResult):
        raise TypeError("AsyncJev.evaluate returned an unexpected result for match")
    return interpret_match(plan, result)


def match(
    jev: Jev,
    left: str,
    right: str,
    *,
    task: str = "Determine whether the two records refer to the same entity.",
    min_confidence: float | None = None,
    model: str | None = None,
) -> MatchResult:
    """Build and execute one entity match through the supplied sync client."""
    plan = build_match(left, right, task=task, min_confidence=min_confidence, model=model)
    return execute_match(jev, plan)


async def amatch(
    jev: AsyncJev,
    left: str,
    right: str,
    *,
    task: str = "Determine whether the two records refer to the same entity.",
    min_confidence: float | None = None,
    model: str | None = None,
) -> MatchResult:
    """Native-async counterpart to :func:`match`."""
    plan = build_match(left, right, task=task, min_confidence=min_confidence, model=model)
    return await aexecute_match(jev, plan)
