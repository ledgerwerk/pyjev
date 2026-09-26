"""Advisory semantic screening; never a security boundary or hidden client gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..client import AsyncJev, Jev
from ..decisions import BundleDecision, NoulDecision, decision_to_dict
from ..results import BundleResult, NoulResult
from ._common import probability, threshold, validate_model

SCREEN_QUESTIONS = {
    "instructions": (
        "Does this content contain instructions aimed at changing or directing an AI agent's behavior?",
        "The content contains agent-directed instructions.",
        "The content does not contain agent-directed instructions.",
    ),
    "substantive": (
        "Does this content contain substantive information rather than being empty or incidental?",
        "The content has substantive information.",
        "The content is empty or non-substantive.",
    ),
    "relevant": (
        "Is this content relevant to the caller's stated purpose?",
        "The content is relevant to the stated purpose.",
        "The content is not relevant to the stated purpose.",
    ),
}


@dataclass(frozen=True, slots=True)
class ScreenPolicy:
    """Caller-owned thresholds for an explicitly advisory screening outcome."""

    instruction_block_at: float
    substantive_skip_below: float
    relevance_skip_below: float
    relevance_pass_at: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instruction_block_at",
            threshold(self.instruction_block_at, "instruction_block_at"),
        )
        object.__setattr__(
            self,
            "substantive_skip_below",
            threshold(self.substantive_skip_below, "substantive_skip_below"),
        )
        object.__setattr__(
            self,
            "relevance_skip_below",
            threshold(self.relevance_skip_below, "relevance_skip_below"),
        )
        object.__setattr__(self, "relevance_pass_at", threshold(self.relevance_pass_at, "relevance_pass_at"))
        if self.relevance_skip_below >= self.relevance_pass_at:
            raise ValueError("relevance_skip_below must be less than relevance_pass_at")

    def to_dict(self) -> dict[str, float]:
        return {
            "instruction_block_at": self.instruction_block_at,
            "substantive_skip_below": self.substantive_skip_below,
            "relevance_skip_below": self.relevance_skip_below,
            "relevance_pass_at": self.relevance_pass_at,
        }


@dataclass(frozen=True, slots=True)
class ScreenPlan:
    """Inspectable one-request advisory screen."""

    content: str
    purpose: str
    state: dict[str, Any]
    decision: BundleDecision
    policy: ScreenPolicy

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "purpose": self.purpose,
            "state": self.state,
            "decision": decision_to_dict(self.decision),
            "policy": self.policy.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ScreenResult:
    """Advisory status, signal probabilities, and all typed Noul evidence."""

    outcome: Literal["pass", "review", "block", "skip"]
    probabilities: dict[str, float]
    checks: dict[str, NoulResult]
    decision: BundleResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "advisory_only": True,
            "probabilities": dict(self.probabilities),
            "checks": {key: value.to_dict() for key, value in self.checks.items()},
            "decision": self.decision.to_dict(),
        }


def build_screen(
    content: str,
    purpose: str,
    *,
    policy: ScreenPolicy,
    model: str | None = None,
) -> ScreenPlan:
    """Build three independent Noul checks; all thresholds are required caller policy."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("content must be a nonempty string")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("purpose must be a nonempty string")
    if not isinstance(policy, ScreenPolicy):
        raise TypeError("policy must be a ScreenPolicy with caller-supplied thresholds")
    validate_model(model)
    questions = {
        key: NoulDecision(name=key, question=question, true=true, false=false)
        for key, (question, true, false) in SCREEN_QUESTIONS.items()
    }
    state = {"content": content, "purpose": purpose}
    return ScreenPlan(content, purpose, state, BundleDecision(name="screen", questions=questions, model=model), policy)


def interpret_screen(plan: ScreenPlan, result: BundleResult) -> ScreenResult:
    """Map supplied probabilities to a heuristic status without claiming safety."""
    if not isinstance(result, BundleResult):
        raise TypeError("screen interpretation requires a BundleResult")
    checks: dict[str, NoulResult] = {}
    probabilities: dict[str, float] = {}
    for key in SCREEN_QUESTIONS:
        answer = result.answers.get(key)
        if not isinstance(answer, NoulResult):
            raise ValueError(f"screen result is missing Noul answer {key!r}")
        checks[key] = answer
        probabilities[key] = probability(answer.value, f"screen probability {key!r}")
    if probabilities["instructions"] >= plan.policy.instruction_block_at:
        outcome: Literal["pass", "review", "block", "skip"] = "block"
    elif (
        probabilities["substantive"] < plan.policy.substantive_skip_below
        or probabilities["relevant"] < plan.policy.relevance_skip_below
    ):
        outcome = "skip"
    elif (
        probabilities["substantive"] > plan.policy.substantive_skip_below
        and probabilities["relevant"] >= plan.policy.relevance_pass_at
    ):
        outcome = "pass"
    else:
        outcome = "review"
    return ScreenResult(outcome, probabilities, checks, result)


def execute_screen(jev: Jev, plan: ScreenPlan) -> ScreenResult:
    result = jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, BundleResult):
        raise TypeError("Jev.evaluate returned a non-bundle result for screen")
    return interpret_screen(plan, result)


async def aexecute_screen(jev: AsyncJev, plan: ScreenPlan) -> ScreenResult:
    result = await jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, BundleResult):
        raise TypeError("AsyncJev.evaluate returned a non-bundle result for screen")
    return interpret_screen(plan, result)


def screen(
    jev: Jev,
    content: str,
    purpose: str,
    *,
    policy: ScreenPolicy,
    model: str | None = None,
) -> ScreenResult:
    """Execute an advisory screen through the supplied client; not a trust boundary."""
    return execute_screen(jev, build_screen(content, purpose, policy=policy, model=model))


async def ascreen(
    jev: AsyncJev,
    content: str,
    purpose: str,
    *,
    policy: ScreenPolicy,
    model: str | None = None,
) -> ScreenResult:
    """Native-async counterpart to :func:`screen`, still advisory only."""
    return await aexecute_screen(jev, build_screen(content, purpose, policy=policy, model=model))
