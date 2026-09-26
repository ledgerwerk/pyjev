from __future__ import annotations

import asyncio

import pytest

from pyjev import BundleResult, NoulResult
from pyjev.recipes.rerank import (
    RerankCandidate,
    RerankPlan,
    arerank,
    build_rerank,
    interpret_rerank,
    rerank,
)


def candidates(count: int) -> list[RerankCandidate]:
    return [RerankCandidate(f"doc-{index}", f"Candidate text {index}") for index in range(count)]


def bundle(values: dict[str, float]) -> BundleResult:
    answers = {
        key: NoulResult(value, "test-model", {"input_tokens": 1}, {"noul": value}, "rerank-request")
        for key, value in values.items()
    }
    return BundleResult(answers, "test-model", {"input_tokens": len(values)}, {}, "rerank-request")


class FakeJev:
    def __init__(self, probabilities: dict[str, float]):
        self.probabilities = probabilities
        self.calls = []

    def evaluate(self, decision, *, state):
        self.calls.append((decision, state))
        answers = {}
        for candidate_id in decision.questions:
            candidate_index = int(candidate_id.removeprefix("relevant_"))
            answers[candidate_id] = NoulResult(
                self.probabilities[f"doc-{candidate_index}"],
                "test-model",
                {},
                {"noul": self.probabilities[f"doc-{candidate_index}"]},
                "rerank-request",
            )
        return BundleResult(answers, "test-model", {}, {}, "rerank-request")


class FakeAsyncJev(FakeJev):
    async def evaluate(self, decision, *, state):
        return super().evaluate(decision, state=state)


def test_rerank_plan_creates_independent_nouls_in_deterministic_chunks():
    plan = build_rerank("retries", candidates(5), chunk_size=2, min_relevance=0.7, model="pinned")
    assert isinstance(plan, RerankPlan)
    assert [len(chunk.decision.questions) for chunk in plan.chunks] == [2, 2, 1]
    assert [candidate.id for candidate in plan.chunks[1].candidates] == ["doc-2", "doc-3"]
    assert all(
        type(question).__name__ == "NoulDecision"
        for chunk in plan.chunks
        for question in chunk.decision.questions.values()
    )
    assert plan.chunks[0].decision.model == "pinned"
    assert len(plan.to_dict()["chunks"]) == 3


def test_rerank_uses_independent_probabilities_and_stable_tie_order():
    plan = build_rerank("retries", candidates(4), chunk_size=2, min_relevance=0.7)
    decisions = [
        bundle({"relevant_0000": 0.9, "relevant_0001": 0.9}),
        bundle({"relevant_0002": 0.1, "relevant_0003": 0.8}),
    ]
    result = interpret_rerank(plan, decisions)
    assert [item.id for item in result.ranked] == ["doc-0", "doc-1", "doc-3", "doc-2"]
    assert [item.id for item in result.results if item.relevant] == ["doc-0", "doc-1", "doc-3"]
    assert result.results[2].relevant is False
    assert result.decisions == tuple(decisions)


def test_rerank_execution_dispatches_chunks_in_order_and_keeps_all_evidence():
    fake = FakeJev({"doc-0": 0.2, "doc-1": 0.9, "doc-2": 0.7})
    result = rerank(fake, "query", candidates(3), chunk_size=2)
    assert len(fake.calls) == 2
    assert [call[1]["candidates"][0]["id"] for call in fake.calls] == ["doc-0", "doc-2"]
    assert [item.id for item in result.ranked] == ["doc-1", "doc-2", "doc-0"]
    assert result.results[0].relevant is None
    assert result.decisions[0].request_id == "rerank-request"


def test_rerank_rejects_limits_and_bad_inputs_locally():
    with pytest.raises(ValueError, match="at least one candidate"):
        build_rerank("query", [])
    with pytest.raises(ValueError, match="chunk_size"):
        build_rerank("query", candidates(1), chunk_size=0)
    with pytest.raises(ValueError, match="min_relevance"):
        build_rerank("query", candidates(1), min_relevance=float("nan"))
    with pytest.raises(ValueError, match="duplicate"):
        build_rerank("query", [RerankCandidate("same", "one"), RerankCandidate("same", "two")])


def test_arerank_executes_native_async_chunks():
    async def run() -> None:
        fake = FakeAsyncJev({"doc-0": 0.8, "doc-1": 0.3})
        result = await arerank(fake, "query", candidates(2), chunk_size=1, min_relevance=0.7)
        assert len(fake.calls) == 2
        assert [item.relevant for item in result.results] == [True, False]

    asyncio.run(run())
