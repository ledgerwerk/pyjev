from __future__ import annotations

from types import SimpleNamespace

from pyjev import Jev


class Dumpable(SimpleNamespace):
    def model_dump(self, mode: str = "python"):
        del mode
        return dict(self.__dict__)


class FakeResponse:
    def __init__(self, kind: str):
        self.model = "jev-test"
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


def test_noul_result():
    client = FakeClient()
    jev = Jev(client=client)
    result = jev.ask("Is it billing?", state="charged twice")
    assert result.value == 0.91
    assert result.to_dict()["noul"] == 0.91
    jev.close()
    assert client.closed is False  # injected clients are caller-owned


def test_choice_result_preserves_confidence_and_probabilities():
    jev = Jev(client=FakeClient())
    result = jev.choice(
        "Route it",
        state="checkout fails",
        choices={"billing": None, "engineering": None, "sales": None},
    )
    assert result.value == "engineering"
    assert result.confidence == 0.93
    assert result.probabilities["engineering"] == 0.93


def test_score_result():
    jev = Jev(client=FakeClient())
    result = jev.score("Urgency?", state="prod down", levels=["low", "normal", "urgent", "critical"])
    assert result.value == 2.7
    assert result.confidence == 0.88
    assert result.legend[3] == "critical"


def test_run_keeps_mixed_request_shape():
    jev = Jev(client=FakeClient())
    result = jev.run(
        state="hello",
        questions={"q": {"type": "noul", "instructions": "Greeting?"}},
    )
    assert result["model"] == "jev-test"


def test_models():
    jev = Jev(client=FakeClient())
    assert jev.models()[0]["name"] == "jev-test"
