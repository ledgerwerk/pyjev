from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest
from typesafe_sdk import AsyncTypeSafeClient, TypeSafeClient

from pyjev import AsyncJev, BundleResult, ChoiceResult, Jev, NoulResult
from pyjev.recipes.classify import (
    OTHER_LABEL,
    ClassifyPlan,
    Label,
    aclassify,
    build_classify,
    classify,
    interpret_classify,
)


class Dumpable(SimpleNamespace):
    def model_dump(self, mode="python"):
        del mode
        return dict(self.__dict__)


class FakeResponse:
    model = "classify-model"
    request_id = "classify-request"
    usage = Dumpable(input_tokens=5, output_tokens=2)

    def __init__(self, *, choices=None, nouls=None):
        self.choices = choices or {}
        self.nouls = nouls or {}
        self.scores = {}

    def model_dump(self, mode="python"):
        del mode
        return {"model": self.model, "request_id": self.request_id}


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def system_one(self, *, state, questions, model=None):
        self.calls.append((state, questions, model))
        return self.response

    def close(self):
        pass


class FakeAsyncClient(FakeClient):
    async def system_one(self, *, state, questions, model=None):
        self.calls.append((state, questions, model))
        return self.response

    async def aclose(self):
        pass


def make_choice(value: str, probabilities: dict[str, float], confidence: float = 0.9) -> ChoiceResult:
    return ChoiceResult(value, confidence, probabilities, "test-model", {}, {"choice": value}, "synthetic")


def make_noul(value: float) -> NoulResult:
    return NoulResult(value, "test-model", {}, {"noul": value}, "synthetic")


def make_bundle(values: dict[str, float]) -> BundleResult:
    return BundleResult(
        {key: make_noul(value) for key, value in values.items()},
        "test-model",
        {"input_tokens": 8},
        {},
        "synthetic",
    )


def test_single_classification_has_explicit_other_and_confidence_policy():
    plan = build_classify(
        "route support tickets",
        [Label("billing", "Payment issues"), Label("technical", "Product issues")],
        include_other=True,
        min_confidence=0.8,
        model="pinned-model",
    )
    assert isinstance(plan, ClassifyPlan)
    assert plan.decision.options[OTHER_LABEL] is not None
    assert plan.decision.model == "pinned-model"
    result = interpret_classify(
        plan,
        make_choice(OTHER_LABEL, {"billing": 0.05, "technical": 0.05, OTHER_LABEL: 0.9}),
    )
    assert result.other_selected is True
    assert result.selected_id is None
    assert result.action == "other"
    assert result.decision.value == OTHER_LABEL


def test_single_classification_without_caller_threshold_is_review_only():
    plan = build_classify("categorize", ["billing", "technical"])
    result = interpret_classify(plan, make_choice("billing", {"billing": 0.7, "technical": 0.3}))
    assert result.selected_id == "billing"
    assert result.action == "review"


def test_multi_label_is_independent_and_keeps_unclear_middle_band():
    plan = build_classify(
        "tag content",
        [("billing", "payments"), ("security", "security concerns"), ("product", "product feedback")],
        mode="multi",
        positive_at=0.75,
        negative_below=0.25,
    )
    assert list(plan.decision.questions) == ["label_0000", "label_0001", "label_0002"]
    result = interpret_classify(plan, make_bundle({"label_0000": 0.9, "label_0001": 0.1, "label_0002": 0.5}))
    assert [label.verdict for label in result.labels] == ["positive", "negative", "unclear"]
    assert result.action == "review"
    assert result.labels[2].decision.value == 0.5


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"mode": "multi"}, "requires positive_at"),
        ({"mode": "multi", "positive_at": 0.5, "negative_below": 0.5}, "less than"),
        ({"include_other": True, "min_confidence": 0.8, "positive_at": 0.5}, "only valid in multi-label"),
    ],
)
def test_invalid_classify_policy_fails_during_planning(options, message):
    with pytest.raises(ValueError, match=message):
        build_classify("task", ["one", "two"], **options)


def test_single_classification_requires_an_escape_for_one_label():
    with pytest.raises(ValueError, match="at least two labels or an explicit other option"):
        build_classify("task", ["one"])


def test_classify_executes_one_sdk_bundle_and_preserves_model_usage():
    response = FakeResponse(
        choices={
            "answer": Dumpable(
                type="choice",
                choice="technical",
                confidence=0.9,
                probabilities={"billing": 0.1, "technical": 0.9},
            )
        }
    )
    client = FakeClient(response)
    result = classify(Jev(client=cast(TypeSafeClient, client)), "route issue", ["billing", "technical"], model="pinned")
    assert len(client.calls) == 1
    assert client.calls[0][2] == "pinned"
    assert result.selected_id == "technical"
    assert result.decision.request_id == "classify-request"


def test_aclassify_runs_with_native_async_client():
    async def run() -> None:
        response = FakeResponse(nouls={"label_0000": Dumpable(type="noul", noul=0.9)})
        client = FakeAsyncClient(response)
        result = await aclassify(
            AsyncJev(client=cast(AsyncTypeSafeClient, client)),
            "tag item",
            ["billing"],
            mode="multi",
            positive_at=0.8,
            negative_below=0.2,
        )
        assert result.labels[0].verdict == "positive"
        assert len(client.calls) == 1

    asyncio.run(run())
