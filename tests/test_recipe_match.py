from __future__ import annotations

import asyncio

import pytest

from pyjev import ChoiceResult
from pyjev.recipes.match import MATCH_OPTIONS, MatchPlan, amatch, build_match, interpret_match, match


def choice(value: str, *, confidence: float = 0.9) -> ChoiceResult:
    return ChoiceResult(
        value=value,
        confidence=confidence,
        probabilities={value: confidence, **{key: (1 - confidence) / 2 for key in MATCH_OPTIONS if key != value}},
        model="test-model",
        usage={"input_tokens": 2},
        raw={"choice": value},
        request_id="match-request",
    )


class FakeJev:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def evaluate(self, decision, *, state):
        self.calls.append((decision, state))
        return self.result


class FakeAsyncJev(FakeJev):
    async def evaluate(self, decision, *, state):
        self.calls.append((decision, state))
        return self.result


def test_match_plan_has_explicit_unclear_and_inspectable_inputs():
    plan = build_match("Alice Smith, 1 Main St", "A. Smith, 1 Main Street", min_confidence=0.8, model="pinned")
    assert isinstance(plan, MatchPlan)
    assert set(plan.decision.options) == {"same", "unclear", "different"}
    assert plan.decision.model == "pinned"
    assert plan.to_dict()["state"]["left"] == "Alice Smith, 1 Main St"


def test_unclear_is_always_review_and_full_choice_evidence_is_retained():
    plan = build_match("record A", "record B", min_confidence=0.5)
    result = interpret_match(plan, choice("unclear", confidence=0.95))
    assert result.verdict == "unclear"
    assert result.action == "review"
    assert result.decision.request_id == "match-request"
    assert result.probabilities["unclear"] == 0.95


def test_threshold_is_required_for_automatic_match_or_nonmatch():
    no_policy = interpret_match(build_match("a", "b"), choice("same"))
    match = interpret_match(build_match("a", "b", min_confidence=0.8), choice("same"))
    different = interpret_match(build_match("a", "b", min_confidence=0.8), choice("different"))
    low = interpret_match(build_match("a", "b", min_confidence=0.95), choice("same", confidence=0.9))
    assert no_policy.action == "review"
    assert match.action == "auto_match"
    assert different.action == "auto_different"
    assert low.action == "review"


def test_invalid_match_inputs_fail_before_execution():
    with pytest.raises(ValueError, match="left"):
        build_match("", "b")
    with pytest.raises(ValueError, match="min_confidence"):
        build_match("a", "b", min_confidence=2)


def test_match_wrapper_evaluates_once_and_preserves_typed_result():
    expected = choice("same")
    client = FakeJev(expected)
    result = match(client, "source", "candidate", min_confidence=0.8)
    assert len(client.calls) == 1
    assert client.calls[0][0].name == "match"
    assert result.decision is expected


def test_amatch_uses_native_async_evaluator():
    async def run() -> None:
        expected = choice("different")
        client = FakeAsyncJev(expected)
        result = await amatch(client, "source", "candidate", min_confidence=0.8)
        assert result.action == "auto_different"
        assert len(client.calls) == 1

    asyncio.run(run())
