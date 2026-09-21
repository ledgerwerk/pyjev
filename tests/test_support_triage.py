from __future__ import annotations

from pathlib import Path
from typing import Any

from examples.support_triage import (
    CONFIG,
    DECISION,
    composite_score,
    run_triage,
)
from pyjev import BundleResult, ChoiceResult, NoulResult, ScoreResult


class FakeJev:
    def __init__(self, result: BundleResult) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any], Path | str, str | None]] = []

    def decide(
        self,
        name: str,
        *,
        state: dict[str, Any],
        config: Path | str,
        model: str | None,
    ) -> BundleResult:
        self.calls.append((name, state, config, model))
        return self.result


def choice(value: str, confidence: float) -> ChoiceResult:
    return ChoiceResult(
        value=value,
        confidence=confidence,
        probabilities={value: 0.90, "other": 0.10},
        model="fake-model",
        usage={},
        raw={"choice": value},
    )


def score(value: float, confidence: float) -> ScoreResult:
    return ScoreResult(
        value=value,
        confidence=confidence,
        probabilities={0: 0.1, 1: 0.2, 2: 0.7},
        legend={0: "low", 1: "normal", 2: "high"},
        model="fake-model",
        usage={},
        raw={"score": value},
    )


def noul(value: float) -> NoulResult:
    return NoulResult(value=value, model="fake-model", usage={}, raw={"noul": value})


def bundle(
    *,
    intent: str = "bug_report",
    intent_confidence: float = 0.90,
    severity: float = 2.0,
    severity_confidence: float = 0.90,
    repro: float = 0.80,
    refund: float = 0.10,
    frustration: float = 1.0,
    complexity: float = 1.0,
) -> BundleResult:
    return BundleResult(
        answers={
            "intent": choice(intent, intent_confidence),
            "complexity": score(complexity, 0.80),
            "bug-severity": score(severity, severity_confidence),
            "has-repro": noul(repro),
            "refund-requested": noul(refund),
            "frustration": score(frustration, 0.80),
        },
        model="fake-model",
        usage={"input_tokens": 1},
        raw={},
        request_id="request-1",
    )


def test_one_bundle_request_preserves_typed_children_and_escalates_bug() -> None:
    fake = FakeJev(bundle())
    report = run_triage(fake, state={"message": "checkout fails"})

    assert len(fake.calls) == 1
    assert fake.calls[0][0] == DECISION
    assert fake.calls[0][1] == {"message": "checkout fails"}
    assert fake.calls[0][2] == CONFIG
    assert isinstance(report.result.answers["intent"], ChoiceResult)
    assert isinstance(report.result.answers["complexity"], ScoreResult)
    assert isinstance(report.result.answers["has-repro"], NoulResult)
    assert report.result.request_id == "request-1"
    assert report.outcome.route == "engineering_escalation"


def test_low_intent_confidence_routes_to_human() -> None:
    report = run_triage(FakeJev(bundle(intent_confidence=0.49)), state={})

    assert report.outcome.route == "human_review"
    assert "intent" in report.outcome.reason


def test_order_status_uses_deterministic_handler_and_ignores_irrelevant_answers() -> None:
    report = run_triage(
        FakeJev(
            bundle(
                intent="order_status",
                severity=0.0,
                severity_confidence=0.10,
                repro=1.0,
                refund=1.0,
            )
        ),
        state={"message": "where is my order"},
    )

    assert report.outcome.route == "order_lookup"


def test_bug_route_requires_severity_confidence_and_reproducibility() -> None:
    uncertain = run_triage(FakeJev(bundle(severity_confidence=0.49)), state={})
    not_reproducible = run_triage(FakeJev(bundle(repro=0.60)), state={})

    assert uncertain.outcome.route == "human_review"
    assert not_reproducible.outcome.route == "bug_backlog"


def test_billing_route_uses_refund_probability() -> None:
    refund = run_triage(FakeJev(bundle(intent="billing", refund=0.71)), state={})
    ordinary = run_triage(FakeJev(bundle(intent="billing", refund=0.70)), state={})

    assert refund.outcome.route == "billing_refund_review"
    assert ordinary.outcome.route == "billing_support"


def test_frustration_sets_cross_cutting_priority_flag() -> None:
    report = run_triage(FakeJev(bundle(intent="feature_request", frustration=1.51)), state={})

    assert report.outcome.route == "feature_intake"
    assert report.outcome.priority is True


def test_composite_score_normalizes_and_weights_atomic_scores() -> None:
    scores = {"complexity": score(1.0, 0.8), "bug-severity": score(2.0, 0.8)}

    assert composite_score(scores, {"complexity": 0.25, "bug-severity": 0.75}) == 0.875


def test_changing_weights_does_not_change_jev_request() -> None:
    state = {"message": "same request"}
    first_fake = FakeJev(bundle())
    second_fake = FakeJev(bundle())

    first = run_triage(first_fake, state=state, weights={"complexity": 0.2, "bug-severity": 0.6, "frustration": 0.2})
    second = run_triage(second_fake, state=state, weights={"complexity": 0.6, "bug-severity": 0.2, "frustration": 0.2})

    assert first_fake.calls[0][:3] == second_fake.calls[0][:3]
    assert first.attention_score != second.attention_score
