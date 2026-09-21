"""Demonstrate routing, scoring, confidence gates, and fan-out in one bundle."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyjev import BundleResult, ChoiceResult, Jev, NoulResult, ScoreResult

CONFIG = Path(__file__).with_name(".pyjev.toml")
DECISION = "support-triage"
MIN_INTENT_CONFIDENCE = 0.50
MIN_SEVERITY_CONFIDENCE = 0.50
REFUND_PROBABILITY = 0.70
REPRODUCIBILITY_PROBABILITY = 0.60
PRIORITY_FRUSTRATION = 1.50
TRIAGE_WEIGHTS = {
    "complexity": 0.25,
    "bug-severity": 0.50,
    "frustration": 0.25,
}
STATE = {
    "customer": "Mira",
    "message": (
        "Every checkout attempt returns a 500 error after the latest release. "
        "The customer included a reproducible sequence and asks for a credit."
    ),
    "account": "acme-example",
    "recent_changes": ["checkout validation", "payment provider timeout"],
}


@dataclass(frozen=True, slots=True)
class TriageOutcome:
    route: str
    reason: str
    priority: bool


@dataclass(frozen=True, slots=True)
class TriageReport:
    result: BundleResult
    outcome: TriageOutcome
    attention_score: float


def _answers(
    result: BundleResult,
) -> tuple[ChoiceResult, ScoreResult, ScoreResult, NoulResult, NoulResult, ScoreResult]:
    intent = result.answers["intent"]
    complexity = result.answers["complexity"]
    severity = result.answers["bug-severity"]
    repro = result.answers["has-repro"]
    refund = result.answers["refund-requested"]
    frustration = result.answers["frustration"]
    if not isinstance(intent, ChoiceResult):
        raise TypeError(f"intent must be ChoiceResult, got {type(intent).__name__}")
    if not isinstance(complexity, ScoreResult):
        raise TypeError(f"complexity must be ScoreResult, got {type(complexity).__name__}")
    if not isinstance(severity, ScoreResult):
        raise TypeError(f"bug-severity must be ScoreResult, got {type(severity).__name__}")
    if not isinstance(repro, NoulResult):
        raise TypeError(f"has-repro must be NoulResult, got {type(repro).__name__}")
    if not isinstance(refund, NoulResult):
        raise TypeError(f"refund-requested must be NoulResult, got {type(refund).__name__}")
    if not isinstance(frustration, ScoreResult):
        raise TypeError(f"frustration must be ScoreResult, got {type(frustration).__name__}")
    return intent, complexity, severity, repro, refund, frustration


def normalized_score(result: ScoreResult) -> float:
    """Normalize an ordered Score to the inclusive range from zero to one."""
    return result.value / max(result.legend)


def composite_score(scores: Mapping[str, ScoreResult], weights: Mapping[str, float]) -> float:
    """Apply caller-owned weights to normalized atomic scores."""
    if set(scores) != set(weights):
        raise ValueError("scores and weights must contain the same dimensions")
    if not weights or abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("weights must be non-empty and sum to one")
    return sum(weights[name] * normalized_score(scores[name]) for name in weights)


def route_support(result: BundleResult) -> TriageOutcome:
    """Apply deterministic application policy to a support-triage result."""
    intent, _complexity, severity, repro, refund, frustration = _answers(result)
    priority = frustration.value > PRIORITY_FRUSTRATION

    if intent.confidence < MIN_INTENT_CONFIDENCE:
        return TriageOutcome("human_review", "low-confidence intent classification", priority)

    if intent.value == "order_status":
        return TriageOutcome("order_lookup", "high-confidence order-status intent", priority)
    if intent.value == "billing":
        if refund.value > REFUND_PROBABILITY:
            return TriageOutcome("billing_refund_review", "refund probability cleared the billing threshold", priority)
        return TriageOutcome("billing_support", "billing intent without a likely refund", priority)
    if intent.value == "bug_report":
        if severity.confidence < MIN_SEVERITY_CONFIDENCE:
            return TriageOutcome("human_review", "low-confidence bug severity", priority)
        if severity.value > 1.5 and repro.value > REPRODUCIBILITY_PROBABILITY:
            return TriageOutcome(
                "engineering_escalation",
                "high-confidence severe bug with reproducible steps",
                priority,
            )
        return TriageOutcome("bug_backlog", "bug does not meet escalation policy", priority)
    if intent.value == "feature_request":
        return TriageOutcome("feature_intake", "feature-request intent", priority)
    return TriageOutcome("account_support", "account-support intent", priority)


def run_triage(
    jev: Any,
    *,
    state: Mapping[str, Any],
    config: str | Path = CONFIG,
    model: str | None = None,
    weights: Mapping[str, float] = TRIAGE_WEIGHTS,
) -> TriageReport:
    """Evaluate the bundle once, then apply only deterministic Python policy."""
    result = jev.decide(DECISION, state=dict(state), config=config, model=model)
    if not isinstance(result, BundleResult):
        raise TypeError(f"Expected BundleResult, got {type(result).__name__}")
    _intent, complexity, severity, _repro, _refund, frustration = _answers(result)
    attention_score = composite_score(
        {"complexity": complexity, "bug-severity": severity, "frustration": frustration},
        weights,
    )
    return TriageReport(result, route_support(result), attention_score)


def main() -> None:
    print("=== Support Triage: Four Decision Patterns ===")
    print("One Jev request asks all triage questions in parallel.")
    print("Python then applies confidence gates and deterministic routing policy.\n")
    print("State sent to Jev:")
    print(json.dumps(STATE, indent=2))

    with Jev() as jev:
        report = run_triage(jev, state=STATE)

    intent, complexity, severity, repro, refund, frustration = _answers(report.result)
    print("\nStructured results:")
    print(f"  intent:       {intent.value:<24} confidence={intent.confidence:.2f}")
    print(f"  complexity:   {complexity.value:>5.2f}                 confidence={complexity.confidence:.2f}")
    print(f"  bug severity: {severity.value:>5.2f}                 confidence={severity.confidence:.2f}")
    print(f"  repro:        {repro.value:.2f}")
    print(f"  refund:       {refund.value:.2f}                 (used only for billing routes)")
    print(f"  frustration:  {frustration.value:.2f}")
    print(f"  attention:    {report.attention_score:.2f}                 (caller-owned composite score)")
    print(f"\nroute: {report.outcome.route}")
    print(f"reason: {report.outcome.reason}")
    print(f"priority flag: {'yes' if report.outcome.priority else 'no'}")
    print("requests: 1")
    print(f"model: {report.result.model}")
    if report.result.request_id:
        print(f"request_id: {report.result.request_id}")


if __name__ == "__main__":
    main()
