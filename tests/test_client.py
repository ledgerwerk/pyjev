from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from typesafe_sdk import TypeSafeClient

from pyjev import Jev


class Dumpable(SimpleNamespace):
    def model_dump(self, mode: str = "python"):
        del mode
        return dict(self.__dict__)


class FakeResponse:
    def __init__(self, kind: str):
        self.model = "jev-test"
        self.request_id = "request-123"
        self.usage = Dumpable(input_tokens=10, output_tokens=2)
        self.nouls = {}
        self.choices = {}
        self.scores = {}

        if kind == "noul":
            self.nouls["answer"] = Dumpable(type="noul", noul=0.91)
        elif kind == "choice":
            self.choices["answer"] = Dumpable(
                type="choice",
                choice="engineering",
                confidence=0.93,
                probabilities={"billing": 0.05, "engineering": 0.93, "sales": 0.02},
            )
        elif kind == "score":
            self.scores["answer"] = Dumpable(
                type="score",
                score=2.7,
                confidence=0.88,
                probabilities={0: 0.0, 1: 0.05, 2: 0.2, 3: 0.75},
                legend={0: "low", 1: "normal", 2: "urgent", 3: "critical"},
            )

    def model_dump(self, mode: str = "python"):
        del mode
        return {"model": self.model, "answers": {}}


class FakeModels:
    def list(self):
        return SimpleNamespace(models=(Dumpable(name="jev-test", description="test", release_date="2026-01-01"),))


class FakeClient:
    def __init__(self):
        self.models = FakeModels()
        self.closed = False
        self.calls = []

    def system_one(self, *, state, questions, model=None):
        self.calls.append((state, questions, model))
        question = next(iter(questions.values()))
        if isinstance(question, dict):
            kind = question["type"]
        else:
            kind = question.type
        return FakeResponse(kind)

    def close(self):
        self.closed = True


def _as_client(client: FakeClient) -> TypeSafeClient:
    return cast(TypeSafeClient, client)


def test_noul_result():
    client = FakeClient()
    jev = Jev(client=_as_client(client))
    result = jev.ask("Is it billing?", state="charged twice")
    assert result.value == 0.91
    assert result.to_dict()["noul"] == 0.91
    jev.close()
    assert client.closed is False  # injected clients are caller-owned


def test_choice_result_preserves_confidence_and_probabilities():
    jev = Jev(client=_as_client(FakeClient()))
    result = jev.choice(
        "Route it",
        state="checkout fails",
        choices={"billing": None, "engineering": None, "sales": None},
    )
    assert result.value == "engineering"
    assert result.confidence == 0.93
    assert result.probabilities["engineering"] == 0.93


def test_score_result():
    jev = Jev(client=_as_client(FakeClient()))
    result = jev.score("Urgency?", state="prod down", levels=["low", "normal", "urgent", "critical"])
    assert result.value == 2.7
    assert result.confidence == 0.88
    assert result.legend[3] == "critical"


def test_run_keeps_mixed_request_shape():
    jev = Jev(client=_as_client(FakeClient()))
    result = jev.run(
        state="hello",
        questions={"q": {"type": "noul", "instructions": "Greeting?"}},
    )
    assert result["model"] == "jev-test"


def test_models():
    jev = Jev(client=_as_client(FakeClient()))
    assert jev.models()[0]["name"] == "jev-test"


def test_auth_test_uses_one_minimal_sdk_request():
    client = FakeClient()
    result = Jev(client=_as_client(client)).auth_test()
    assert result.value == 0.91
    assert len(client.calls) == 1
    state, questions, model = client.calls[0]
    assert state == "authentication test"
    assert model is None
    question = questions["answer"]
    assert question.type == "noul"
    assert question.instructions == "Is this an authentication test?"


def test_request_id_is_preserved():
    result = Jev(client=_as_client(FakeClient())).ask("Question?", state="state")
    assert result.request_id == "request-123"
    assert result.to_dict()["request_id"] == "request-123"


@pytest.mark.parametrize("choices", [[], ["one"], ["one", "one"]])
def test_invalid_choice_sequence_makes_no_api_call(choices):
    client = FakeClient()
    with pytest.raises(ValueError):
        Jev(client=_as_client(client)).choice("Route?", state="state", choices=choices)
    assert client.calls == []


def test_choice_rejects_256_options_without_api_call():
    client = FakeClient()
    with pytest.raises(ValueError, match="255"):
        Jev(client=_as_client(client)).choice("Route?", state="state", choices=[str(i) for i in range(256)])
    assert client.calls == []


@pytest.mark.parametrize("levels", [[], ["one"], [str(i) for i in range(11)]])
def test_invalid_score_levels_make_no_api_call(levels):
    client = FakeClient()
    with pytest.raises(ValueError, match="2 and 10"):
        Jev(client=_as_client(client)).score("Score?", state="state", levels=levels)
    assert client.calls == []


def test_injected_client_rejects_constructor_options():
    with pytest.raises(ValueError, match="injected client"):
        Jev(client=_as_client(FakeClient()), model="model")


def test_named_decision_dispatch_uses_explicit_model_override(tmp_path):
    config = tmp_path / ".pyjev.toml"
    config.write_text(
        "[decision.route]\ntype='choice'\nquestion='Route?'\nmodel='decision-model'\n"
        "[decision.route.options]\nbilling='Billing'\nengineering='Technical'\n",
        encoding="utf-8",
    )
    client = FakeClient()
    result = Jev(client=_as_client(client)).decide("route", state="ticket", config=config, model="call-model")
    assert result.value == "engineering"
    assert client.calls[-1][2] == "call-model"


def test_named_decision_uses_config_model_when_call_model_absent(tmp_path):
    config = tmp_path / ".pyjev.toml"
    config.write_text(
        "[decision.route]\ntype='choice'\nquestion='Route?'\nmodel='decision-model'\n"
        "[decision.route.options]\nbilling='Billing'\nengineering='Technical'\n",
        encoding="utf-8",
    )
    client = FakeClient()
    Jev(client=_as_client(client)).decide("route", state="ticket", config=config)
    assert client.calls[-1][2] == "decision-model"
