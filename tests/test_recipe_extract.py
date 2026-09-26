from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest
from typesafe_sdk import AsyncTypeSafeClient, TypeSafeClient

from pyjev import AsyncJev, BundleResult, ChoiceResult, Jev
from pyjev.recipes.extract import (
    Field,
    aextract,
    build_extract,
    extract,
    interpret_extract,
    regex_field,
)


class Dumpable(SimpleNamespace):
    def model_dump(self, mode: str = "python"):
        del mode
        return dict(self.__dict__)


class FakeResponse:
    model = "extract-model"
    request_id = "extract-request"
    usage = Dumpable(input_tokens=11, output_tokens=4)

    def __init__(self, field_names: list[str], selected: dict[str, str], confidence: float):
        self.choices = {
            name: Dumpable(
                type="choice",
                choice=selected.get(name, "candidate-0000"),
                confidence=confidence,
                probabilities={selected.get(name, "candidate-0000"): confidence, "__none__": 1 - confidence},
            )
            for name in field_names
        }
        self.nouls = {}
        self.scores = {}

    def model_dump(self, mode: str = "python"):
        del mode
        return {"model": self.model, "request_id": self.request_id}


class FakeClient:
    def __init__(self, *, selected: dict[str, str] | None = None, confidence: float = 0.9):
        self.selected = selected or {}
        self.confidence = confidence
        self.calls = []

    def system_one(self, *, state, questions, model=None):
        self.calls.append((state, questions, model))
        return FakeResponse(list(questions), self.selected, self.confidence)

    def close(self):
        pass


class FakeAsyncClient(FakeClient):
    async def system_one(self, *, state, questions, model=None):
        self.calls.append((state, questions, model))
        return FakeResponse(list(questions), self.selected, self.confidence)

    async def aclose(self):
        pass


def invoice_field(**kwargs: Any) -> Field:
    return regex_field(
        "invoice",
        r"INV-\d+",
        description="the invoice number",
        normalizer=lambda value: int(value.removeprefix("INV-")),
        **kwargs,
    )


def test_regex_field_extracts_unique_candidates_in_source_order():
    plan = build_extract("INV-1004 then INV-1017 then INV-1004", [invoice_field()])
    invoice = plan.fields[0]
    assert invoice.candidates == ("INV-1004", "INV-1017")
    assert invoice.candidate_ids == ("candidate-0000", "candidate-0001")
    assert plan.decision is not None
    assert "__none__" in plan.decision.questions["invoice"].options


def test_extract_skips_empty_fields_and_bundles_remaining_questions_once():
    client = FakeClient()
    fields = [
        invoice_field(),
        regex_field("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", description="the sender email"),
    ]
    result = extract(Jev(client=cast(TypeSafeClient, client)), "INV-1004 sender@example.test", fields)
    assert len(client.calls) == 1
    assert list(client.calls[0][1]) == ["invoice", "email"]
    assert result.fields["invoice"].source_value == "INV-1004"
    assert result.fields["invoice"].normalized_value == 1004
    assert result.fields["invoice"].action == "review"  # no caller gate means no automatic action
    assert result.fields["email"].source_value == "sender@example.test"
    assert isinstance(result.decision, BundleResult)
    assert result.decision.request_id == "extract-request"


def test_all_fields_without_candidates_make_zero_api_calls():
    client = FakeClient()
    fields = [invoice_field(), regex_field("email", r"[\w.+-]+@[\w.-]+", description="the email")]
    result = extract(Jev(client=cast(TypeSafeClient, client)), "No literals in this source", fields)
    assert client.calls == []
    assert result.decision is None
    assert all(value.action == "no_candidates" for value in result.fields.values())


def test_empty_field_is_not_asked_when_other_fields_have_candidates():
    client = FakeClient()
    fields = [
        invoice_field(),
        regex_field("email", r"[\w.+-]+@[\w.-]+", description="the email"),
    ]
    result = extract(Jev(client=cast(TypeSafeClient, client)), "INV-1004", fields)
    assert len(client.calls) == 1
    assert list(client.calls[0][1]) == ["invoice"]
    assert result.fields["email"].action == "no_candidates"


def test_none_selection_returns_none_not_a_generated_value():
    client = FakeClient(selected={"invoice": "__none__"})
    result = extract(Jev(client=cast(TypeSafeClient, client)), "INV-1004", [invoice_field()])
    assert result.fields["invoice"].action == "none"
    assert result.fields["invoice"].source_value is None
    assert result.fields["invoice"].normalized_value is None
    assert result.fields["invoice"].decision is not None


def test_confidence_below_caller_policy_reviews_and_preserves_model_evidence():
    client = FakeClient(confidence=0.6)
    result = extract(
        Jev(client=cast(TypeSafeClient, client)),
        "INV-1004",
        [invoice_field()],
        min_confidence=0.8,
    )
    field = result.fields["invoice"]
    assert field.action == "review"
    assert field.source_value == "INV-1004"
    assert field.normalized_value == 1004
    assert field.decision is not None
    assert field.decision.probabilities["candidate-0000"] == 0.6
    assert result.decision is not None
    assert result.decision.usage == {"input_tokens": 11, "output_tokens": 4}


def test_normalizer_exception_is_safe_and_keeps_literal_and_choice_evidence():
    def broken(_: str) -> int:
        raise ValueError("secret customer detail")

    client = FakeClient()
    field = regex_field("invoice", r"INV-\d+", description="invoice", normalizer=broken)
    result = extract(Jev(client=cast(TypeSafeClient, client)), "INV-1004", [field])
    outcome = result.fields["invoice"]
    assert outcome.action == "review"
    assert outcome.source_value == "INV-1004"
    assert outcome.normalized_value is None
    assert outcome.normalization_error is not None
    assert "secret customer detail" not in outcome.normalization_error
    assert outcome.decision is not None


def test_candidate_cap_fails_before_client_request():
    client = FakeClient()
    field = regex_field("invoice", r"INV-\d+", description="invoice", max_candidates=1)
    with pytest.raises(ValueError, match="max_candidates=1"):
        extract(Jev(client=cast(TypeSafeClient, client)), "INV-1 INV-2", [field])
    assert client.calls == []


def test_invalid_regex_group_and_confidence_fail_locally():
    with pytest.raises(ValueError, match="group number"):
        regex_field("invoice", r"INV-\d+", description="invoice", group=1)
    with pytest.raises(ValueError, match="min_confidence"):
        build_extract("INV-1", [invoice_field()], min_confidence=1.5)


def test_interpret_extract_handles_none_and_normalizer_failure_from_synthetic_bundle():
    plan = build_extract("INV-1004", [invoice_field()], min_confidence=0.8)
    assert plan.decision is not None
    response = FakeResponse(["invoice"], {"invoice": "__none__"}, 0.5)
    choice = ChoiceResult(
        value=response.choices["invoice"].choice,
        confidence=response.choices["invoice"].confidence,
        probabilities=response.choices["invoice"].probabilities,
        model="extract-model",
        usage={"input_tokens": 1, "output_tokens": 1},
        raw={"choice": "__none__"},
    )
    bundle = BundleResult({"invoice": choice}, "extract-model", {"input_tokens": 1}, {}, "synthetic")
    result = interpret_extract(plan, bundle)
    assert result.fields["invoice"].action == "review"
    assert result.fields["invoice"].source_value is None


def test_aextract_uses_async_client():
    async def run() -> None:
        client = FakeAsyncClient()
        result = await aextract(
            AsyncJev(client=cast(AsyncTypeSafeClient, client)),
            "INV-1004",
            [invoice_field()],
            min_confidence=0.8,
        )
        assert len(client.calls) == 1
        assert result.fields["invoice"].action == "auto"

    asyncio.run(run())
