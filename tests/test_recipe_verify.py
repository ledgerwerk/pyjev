from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest
from typesafe_sdk import AsyncTypeSafeClient, TypeSafeClient

from pyjev import AsyncJev, BundleResult, ChoiceResult, Jev
from pyjev.recipes.verify import (
    Claim,
    Evidence,
    VerifyPlan,
    averify,
    build_verify,
    interpret_verify,
    verify,
)


class Dumpable(SimpleNamespace):
    def model_dump(self, mode: str = "python"):
        del mode
        return dict(self.__dict__)


class FakeResponse:
    model = "verify-model"
    request_id = "verify-request"
    usage = Dumpable(input_tokens=20, output_tokens=8)

    def __init__(self, questions, relations, sources, confidence):
        self.choices = {}
        for key in questions:
            if key.startswith("relation_"):
                selected = relations.get(key, "supports")
                options = {"supports": 0.8, "contradicts": 0.1, "says_nothing": 0.1}
            else:
                selected = sources.get(key, "__none__")
                options = {selected: confidence, "__none__": 1 - confidence}
            self.choices[key] = Dumpable(
                type="choice",
                choice=selected,
                confidence=confidence,
                probabilities=options,
            )
        self.nouls = {}
        self.scores = {}

    def model_dump(self, mode: str = "python"):
        del mode
        return {"model": self.model, "request_id": self.request_id}


class FakeClient:
    def __init__(self, *, relations=None, sources=None, confidence=0.9):
        self.relations = relations or {}
        self.sources = sources or {}
        self.confidence = confidence
        self.calls = []

    def system_one(self, *, state, questions, model=None):
        self.calls.append((state, questions, model))
        return FakeResponse(questions, self.relations, self.sources, self.confidence)

    def close(self):
        pass


class FakeAsyncClient(FakeClient):
    async def system_one(self, *, state, questions, model=None):
        self.calls.append((state, questions, model))
        return FakeResponse(questions, self.relations, self.sources, self.confidence)

    async def aclose(self):
        pass


def synthetic_bundle(plan: VerifyPlan, values: dict[str, str], *, confidence: float = 0.9) -> BundleResult:
    answers = {}
    for key, value in values.items():
        answers[key] = ChoiceResult(
            value=value,
            confidence=confidence,
            probabilities={value: confidence, "other": 1 - confidence},
            model="verify-model",
            usage={"input_tokens": 3, "output_tokens": 1},
            raw={"choice": value},
            request_id="synthetic-request",
        )
    return BundleResult(answers, "verify-model", {"input_tokens": 10}, {}, "synthetic-request")


def test_build_verify_normalizes_ids_and_bundles_independent_questions():
    plan = build_verify(
        [Claim("api-claim", "The client retries requests."), "The CLI fetches evidence."],
        [Evidence("readme", "The client retry policy is configured here."), ("source:2", "The CLI uses local input.")],
        model="pinned-model",
    )
    assert isinstance(plan, VerifyPlan)
    assert [claim.claim.id for claim in plan.claims] == ["api-claim", "claim-0001"]
    assert plan.claims[0].relation_key == "relation_0000"
    assert plan.claims[0].source_key == "source_0000"
    assert len(plan.decision.questions) == 4
    assert "source:2" in plan.decision.questions["source_0000"].options
    assert plan.decision.model == "pinned-model"
    assert plan.to_dict()["state"]["evidence"][1]["id"] == "source:2"


def test_relation_mapping_keeps_unsupported_distinct_from_contradicted():
    plan = build_verify(["Claim A", "Claim B", "Claim C"], ["evidence text"])
    values = {
        "relation_0000": "supports",
        "relation_0001": "contradicts",
        "relation_0002": "says_nothing",
    }
    result = interpret_verify(plan, synthetic_bundle(plan, values))
    assert [item.verdict for item in result.results] == ["verified", "contradicted", "unsupported"]
    assert result.summary.to_dict() == {
        "total": 3,
        "verified": 1,
        "contradicted": 1,
        "unsupported": 1,
        "auto_accepted": 0,
        "review": 3,
    }


def test_source_ids_round_trip_and_summary_arithmetic_are_exact():
    plan = build_verify(
        [("c-1", "The change adds retries."), ("c-2", "The package edits docs only.")],
        [("diff-A", "The diff adds client retry handling."), ("docs-B", "Documentation describes installation.")],
        auto_accept=0.85,
    )
    result = interpret_verify(
        plan,
        synthetic_bundle(
            plan,
            {
                "relation_0000": "supports",
                "relation_0001": "contradicts",
                "source_0000": "diff-A",
                "source_0001": "docs-B",
            },
        ),
    )
    assert result.results[0].source_id == "diff-A"
    assert result.results[0].evidence_source == Evidence("diff-A", "The diff adds client retry handling.")
    assert result.results[0].supporting_evidence is not None
    assert result.results[0].action == "auto_accept"
    assert result.results[1].action == "review"
    assert result.summary.total == result.summary.verified + result.summary.contradicted + result.summary.unsupported
    assert result.summary.total == result.summary.auto_accepted + result.summary.review
    assert result.decision.request_id == "synthetic-request"


def test_source_none_prevents_auto_accept_and_retains_choice_result():
    plan = build_verify(["A claim"], [("s1", "First source"), ("s2", "Second source")], auto_accept=0.7)
    result = interpret_verify(
        plan,
        synthetic_bundle(plan, {"relation_0000": "supports", "source_0000": "__none__"}),
    )
    verdict = result.results[0]
    assert verdict.verdict == "verified"
    assert verdict.source_id is None
    assert verdict.evidence_source is None
    assert verdict.action == "review"
    assert verdict.source_result is not None


@pytest.mark.parametrize(
    ("claims", "evidence", "message"),
    [
        ([Claim("same", "A"), Claim("same", "B")], ["source"], "duplicate claim ID"),
        ([Claim("bad id", "A")], ["source"], "claim IDs"),
        (["claim"], [("__none__", "source"), ("good", "source")], "reserved"),
        ([], ["source"], "at least one claim"),
        (["claim"], [], "at least one evidence source"),
    ],
)
def test_invalid_ids_and_empty_inputs_fail_during_planning(claims, evidence, message):
    with pytest.raises(ValueError, match=message):
        build_verify(claims, evidence)


def test_claim_count_limit_is_explicit():
    with pytest.raises(ValueError, match="max_claims"):
        build_verify([f"claim {i}" for i in range(3)], ["source"], max_claims=2)


def test_verify_executes_multiple_claims_in_one_request_and_retains_results():
    client = FakeClient(relations={"relation_0000": "says_nothing", "relation_0001": "contradicts"})
    result = verify(
        Jev(client=cast(TypeSafeClient, client)),
        ["The CLI has a config file.", "This behavior is documented."],
        [("docs", "The docs describe current behavior.")],
    )
    assert len(client.calls) == 1
    assert len(client.calls[0][1]) == 2
    assert [item.verdict for item in result.results] == ["unsupported", "contradicted"]
    assert result.decision.usage == {"input_tokens": 20, "output_tokens": 8}


def test_averify_uses_native_async_client():
    async def run() -> None:
        client = FakeAsyncClient()
        result = await averify(
            AsyncJev(client=cast(AsyncTypeSafeClient, client)),
            ["A claim"],
            ["supplied source"],
            auto_accept=0.8,
        )
        assert result.results[0].action == "auto_accept"
        assert len(client.calls) == 1

    asyncio.run(run())
