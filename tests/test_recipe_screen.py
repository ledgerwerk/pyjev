from __future__ import annotations

import asyncio

import pytest

from pyjev import BundleResult, NoulResult
from pyjev.recipes.screen import (
    ScreenPlan,
    ScreenPolicy,
    ascreen,
    build_screen,
    interpret_screen,
    screen,
)


def make_bundle(values: dict[str, float]) -> BundleResult:
    answers = {
        key: NoulResult(value, "screen-model", {}, {"noul": value}, "screen-request") for key, value in values.items()
    }
    return BundleResult(answers, "screen-model", {"input_tokens": 12}, {}, "screen-request")


def policy() -> ScreenPolicy:
    return ScreenPolicy(
        instruction_block_at=0.8,
        substantive_skip_below=0.2,
        relevance_skip_below=0.15,
        relevance_pass_at=0.7,
    )


def values(*, instructions=0.1, substantive=0.9, relevant=0.8):
    return {"instructions": instructions, "substantive": substantive, "relevant": relevant}


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


def test_screen_plan_is_inspectable_and_requires_explicit_caller_policy():
    plan = build_screen("untrusted content", "summarize safely", policy=policy(), model="pinned")
    assert isinstance(plan, ScreenPlan)
    assert list(plan.decision.questions) == ["instructions", "substantive", "relevant"]
    assert plan.decision.model == "pinned"
    assert plan.to_dict()["state"]["content"] == "untrusted content"
    with pytest.raises(TypeError, match="ScreenPolicy"):
        build_screen("content", "purpose", policy=None)


def test_screen_outcomes_are_deterministic_and_advisory_with_evidence():
    cases = [
        (values(instructions=0.9), "block"),
        (values(substantive=0.1), "skip"),
        (values(relevant=0.1), "skip"),
        (values(), "pass"),
        (values(relevant=0.5), "review"),
    ]
    for signals, expected in cases:
        decision = make_bundle(signals)
        result = interpret_screen(build_screen("content", "purpose", policy=policy()), decision)
        assert result.outcome == expected
        assert result.to_dict()["advisory_only"] is True
        assert result.probabilities == signals
        assert result.decision is decision


def test_screen_policy_validates_order_and_finite_thresholds():
    with pytest.raises(ValueError, match="less than"):
        ScreenPolicy(0.8, 0.2, 0.8, 0.7)
    with pytest.raises(ValueError, match="finite"):
        ScreenPolicy(float("nan"), 0.2, 0.1, 0.8)


def test_screen_wrapper_evaluates_once_and_has_no_implicit_blocking():
    decision = make_bundle(values(relevant=0.5))
    client = FakeJev(decision)
    result = screen(client, "content", "purpose", policy=policy())
    assert result.outcome == "review"
    assert len(client.calls) == 1
    assert client.calls[0][0].name == "screen"


def test_ascreen_uses_async_evaluator_and_remains_advisory():
    async def run() -> None:
        client = FakeAsyncJev(make_bundle(values()))
        result = await ascreen(client, "content", "purpose", policy=policy())
        assert result.outcome == "pass"
        assert result.to_dict()["advisory_only"] is True
        assert len(client.calls) == 1

    asyncio.run(run())
