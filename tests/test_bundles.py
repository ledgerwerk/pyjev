from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from typer.testing import CliRunner
from typesafe_sdk import TypeSafeClient

from pyjev import BundleResult, ChoiceResult, Jev, ScoreResult
from pyjev.cli import app
from pyjev.decisions import BundleDecision, DecisionConfigError, load_decision

runner = CliRunner()


class Dumpable(SimpleNamespace):
    def model_dump(self, mode: str = "python"):
        del mode
        return dict(self.__dict__)


class BundleResponse:
    model = "bundle-model"
    request_id = "request-bundle"
    usage = Dumpable(input_tokens=20, output_tokens=8)

    def __init__(self, names: list[str]):
        self.nouls = {}
        self.choices = {}
        self.scores = {}
        for name in names:
            if name == "refund":
                self.nouls[name] = Dumpable(type="noul", noul=0.81)
            elif name == "route":
                self.choices[name] = Dumpable(
                    type="choice",
                    choice="engineering",
                    confidence=0.91,
                    probabilities={"billing": 0.09, "engineering": 0.91},
                )
            elif name == "urgency":
                self.scores[name] = Dumpable(
                    type="score",
                    score=2.4,
                    confidence=0.87,
                    probabilities={0: 0.1, 1: 0.2, 2: 0.3, 3: 0.4},
                    legend={0: "low", 1: "normal", 2: "urgent", 3: "critical"},
                )

    def model_dump(self, mode: str = "python"):
        del mode
        return {"model": self.model, "request_id": self.request_id}


class BundleClient:
    def __init__(self):
        self.calls = []

    def system_one(self, *, state, questions, model=None):
        self.calls.append((state, questions, model))
        return BundleResponse(list(questions))

    def close(self):
        pass


def _as_client(client: BundleClient) -> TypeSafeClient:
    return cast(TypeSafeClient, client)


def bundle_config(tmp_path: Path, *, child_model: bool = False) -> Path:
    child_model_text = '\nmodel = "child-model"' if child_model else ""
    path = tmp_path / ".pyjev.toml"
    path.write_text(
        f'''[pyjev]
schema = 1

[decision.ticket-triage]
type = "bundle"
model = "bundle-config-model"

[decision.ticket-triage.questions.refund]
type = "noul"
question = "Refund?"
true = "Requests money back"
false = "Does not request money back"

[decision.ticket-triage.questions.route]
type = "choice"
question = "Which team?"{child_model_text}

[decision.ticket-triage.questions.route.options]
billing = "Payments"
engineering = "Technical"

[decision.ticket-triage.questions.urgency]
type = "score"
question = "How urgent?"
levels = ["low", "normal", "urgent", "critical"]
''',
        encoding="utf-8",
    )
    return path


def test_bundle_parser_preserves_child_keys_and_rejects_child_models(tmp_path: Path) -> None:
    decision = load_decision("ticket-triage", bundle_config(tmp_path))
    assert isinstance(decision, BundleDecision)
    assert list(decision.questions) == ["refund", "route", "urgency"]
    with pytest.raises(DecisionConfigError, match="child model"):
        load_decision("ticket-triage", bundle_config(tmp_path, child_model=True))


def test_bundle_uses_one_call_and_preserves_each_result(tmp_path: Path) -> None:
    client = BundleClient()
    result = Jev(client=_as_client(client)).decide(
        "ticket-triage",
        state={"ticket": "down"},
        config=bundle_config(tmp_path),
    )
    assert isinstance(result, BundleResult)
    assert len(client.calls) == 1
    assert list(result.answers) == ["refund", "route", "urgency"]
    route = result.answers["route"]
    assert isinstance(route, ChoiceResult)
    assert route.probabilities["engineering"] == 0.91
    urgency = result.answers["urgency"]
    assert isinstance(urgency, ScoreResult)
    assert urgency.legend[3] == "critical"
    assert result.request_id == "request-bundle"


def test_bundle_cli_rejects_value_and_confidence_before_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("pyjev.cli._run_api", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    path = bundle_config(tmp_path)
    value_result = runner.invoke(app, ["decide", "ticket-triage", "--config", str(path), "--state", "x", "--value"])
    confidence_result = runner.invoke(
        app,
        ["decide", "ticket-triage", "--config", str(path), "--state", "x", "--min-confidence", "0.8"],
    )
    assert value_result.exit_code != 0
    assert "not valid for bundle" in value_result.output
    assert confidence_result.exit_code != 0
    assert "not valid for bundle" in confidence_result.output
