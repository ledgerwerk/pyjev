from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest
from typesafe_sdk import AsyncTypeSafeClient, TypeSafeClient

from pyjev import AsyncJev, BundleResult, ChoiceResult, Jev, NoulResult
from pyjev.recipes.find import Candidate, FindPlan, afind, build_find, find, interpret_find


class Dumpable(SimpleNamespace):
    def model_dump(self, mode: str = "python"):
        del mode
        return dict(self.__dict__)


class FakeResponse:
    model = "test-model"
    request_id = "find-request"
    usage = Dumpable(input_tokens=7, output_tokens=3)

    def __init__(self):
        self.choices = {
            "best": Dumpable(
                type="choice",
                choice="doc-b",
                confidence=0.7,
                probabilities={"doc-a": 0.7, "doc-b": 0.2, "__no_candidate__": 0.1},
            )
        }
        self.nouls = {"exists": Dumpable(type="noul", noul=0.8)}
        self.scores = {}

    def model_dump(self, mode: str = "python"):
        del mode
        return {"model": self.model, "request_id": self.request_id}


class FakeClient:
    def __init__(self):
        self.calls = []

    def system_one(self, *, state, questions, model=None):
        self.calls.append((state, questions, model))
        return FakeResponse()

    def close(self):
        pass


class FakeAsyncClient(FakeClient):
    async def system_one(self, *, state, questions, model=None):
        self.calls.append((state, questions, model))
        return FakeResponse()

    async def aclose(self):
        pass


def make_bundle(*, exists: float, probabilities: dict[str, float]) -> BundleResult:
    choice = ChoiceResult(
        value=max(probabilities, key=probabilities.get),
        confidence=max(probabilities.values()),
        probabilities=probabilities,
        model="test-model",
        usage={"input_tokens": 2, "output_tokens": 1},
        raw={"choice": "candidate"},
        request_id="synthetic-request",
    )
    noul = NoulResult(
        value=exists,
        model="test-model",
        usage={"input_tokens": 2, "output_tokens": 1},
        raw={"noul": exists},
        request_id="synthetic-request",
    )
    return BundleResult(
        answers={"best": choice, "exists": noul},
        model="test-model",
        usage={"input_tokens": 4, "output_tokens": 2},
        raw={"answers": {}},
        request_id="synthetic-request",
    )


def candidates() -> list[Candidate]:
    return [Candidate("doc-a", "Authentication guide"), Candidate("doc-b", "Retry configuration")]


def test_build_find_is_pure_inspectable_and_uses_rank_plus_abstention():
    plan = build_find("Where are retries configured?", candidates(), top_k=1, model="pinned-model")
    assert isinstance(plan, FindPlan)
    assert plan.state["query"] == "Where are retries configured?"
    assert [item["id"] for item in plan.to_dict()["state"]["candidates"]] == ["doc-a", "doc-b"]
    assert list(plan.decision.questions) == ["best", "exists"]
    assert "__no_candidate__" in plan.decision.questions["best"].options
    assert plan.decision.model == "pinned-model"


@pytest.mark.parametrize(
    ("query", "items", "kwargs", "message"),
    [
        (" ", candidates(), {}, "query"),
        ("query", [], {}, "at least one candidate"),
        ("query", [Candidate("bad id", "text")], {}, "candidate IDs"),
        ("query", [Candidate("same", "a"), Candidate("same", "b")], {}, "duplicate"),
        ("query", candidates(), {"top_k": 0}, "top_k"),
        ("query", candidates(), {"found_at": 0.2, "absent_below": 0.3}, "greater"),
    ],
)
def test_find_invalid_input_fails_before_request(query, items, kwargs, message):
    with pytest.raises((TypeError, ValueError), match=message):
        build_find(query, items, **kwargs)


def test_find_candidate_and_choice_cardinality_limits_are_local():
    build_find("query", [Candidate(f"doc-{index}", "text") for index in range(254)])
    with pytest.raises(ValueError, match="at most 254"):
        build_find("query", [Candidate(f"doc-{index}", "text") for index in range(255)])


def test_interpret_find_ranks_probabilities_with_input_order_tie_break_and_keeps_absent_hits():
    plan = build_find("query", candidates(), top_k=2)
    result = interpret_find(plan, make_bundle(exists=0.2, probabilities={"doc-a": 0.6, "doc-b": 0.6}))
    assert [hit.id for hit in result.hits] == ["doc-a", "doc-b"]
    assert result.exists_probability == 0.2
    assert result.exists_verdict == "absent"
    assert result.hits[0].probability == 0.6
    assert result.decision.request_id == "synthetic-request"


def test_interpret_find_maps_partial_and_answered_thresholds():
    plan = build_find("query", candidates(), found_at=0.7, absent_below=0.3)
    partial = interpret_find(plan, make_bundle(exists=0.5, probabilities={"doc-a": 0.8, "doc-b": 0.2}))
    assert partial.exists_verdict == "partial"
    answered = interpret_find(plan, make_bundle(exists=0.7, probabilities={"doc-a": 0.8, "doc-b": 0.2}))
    assert answered.exists_verdict == "answered"


def test_find_executes_one_bundle_request_and_preserves_evidence():
    client = FakeClient()
    jev = Jev(client=cast(TypeSafeClient, client))
    result = find(jev, "Where are retries configured?", candidates(), top_k=1, model="pinned-model")
    assert len(client.calls) == 1
    assert client.calls[0][0]["query"] == "Where are retries configured?"
    assert client.calls[0][2] == "pinned-model"
    assert result.hits[0].id == "doc-a"
    assert result.exists_verdict == "answered"
    assert result.decision.usage == {"input_tokens": 7, "output_tokens": 3}


def test_find_rejects_invalid_query_without_calling_client():
    client = FakeClient()
    with pytest.raises(ValueError, match="query"):
        find(Jev(client=cast(TypeSafeClient, client)), "", candidates())
    assert client.calls == []


def test_afind_uses_async_client_and_one_bundle_request():
    async def run() -> None:
        client = FakeAsyncClient()
        jev = AsyncJev(client=cast(AsyncTypeSafeClient, client))
        result = await afind(jev, "Where are retries configured?", candidates())
        assert result.exists_verdict == "answered"
        assert len(client.calls) == 1

    asyncio.run(run())
