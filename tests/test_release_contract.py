from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import pyjev.cli as cli
from pyjev.cli import EXIT_CONFIDENCE, EXIT_USAGE, app
from pyjev.results import ChoiceResult, ScoreResult

runner = CliRunner()


def choice_result(confidence: float = 0.4) -> ChoiceResult:
    return ChoiceResult(
        value="engineering",
        confidence=confidence,
        probabilities={"billing": 0.1, "engineering": 0.9},
        model="test",
        usage={},
        raw={"choice": "engineering", "confidence": confidence},
        request_id="request-1",
    )


def score_result(confidence: float = 0.4) -> ScoreResult:
    return ScoreResult(
        value=1.5,
        confidence=confidence,
        probabilities={0: 0.2, 1: 0.8},
        legend={0: "low", 1: "high"},
        model="test",
        usage={},
        raw={"score": 1.5, "confidence": confidence},
        request_id="request-1",
    )


def test_output_conflict_is_rejected_before_api(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("API should not be called")

    monkeypatch.setattr(cli, "_run_api", unexpected)
    result = runner.invoke(
        app,
        [
            "choice",
            "Route?",
            "--state",
            "state",
            "--option",
            "billing",
            "--option",
            "engineering",
            "--json",
            "--value",
        ],
    )
    assert result.exit_code == EXIT_USAGE
    assert "either --json or --value" in result.output


def test_invalid_confidence_is_rejected_before_api(monkeypatch):
    monkeypatch.setattr(cli, "_run_api", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    result = runner.invoke(
        app,
        [
            "choice",
            "Route?",
            "--state",
            "state",
            "--option",
            "billing",
            "--option",
            "engineering",
            "--min-confidence",
            "1.1",
        ],
    )
    assert result.exit_code == EXIT_USAGE


def test_invalid_cardinality_is_rejected_before_api(monkeypatch):
    monkeypatch.setattr(cli, "_run_api", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    result = runner.invoke(app, ["score", "Urgency?", "--state", "state", "--level", "only"])
    assert result.exit_code == EXIT_USAGE
    assert "between 2 and 10" in result.output


def test_failed_value_gate_has_no_actionable_stdout(monkeypatch):
    monkeypatch.setattr(cli, "_run_api", lambda *args, **kwargs: choice_result())
    result = runner.invoke(
        app,
        [
            "choice",
            "Route?",
            "--state",
            "state",
            "--option",
            "billing",
            "--option",
            "engineering",
            "--value",
            "--min-confidence",
            "0.85",
        ],
    )
    assert result.exit_code == EXIT_CONFIDENCE
    assert result.stdout == ""
    assert "0.40" in result.stderr
    assert "0.85" in result.stderr


def test_failed_json_gate_returns_explicit_envelope(monkeypatch):
    monkeypatch.setattr(cli, "_run_api", lambda *args, **kwargs: score_result())
    result = runner.invoke(
        app,
        [
            "score",
            "Urgency?",
            "--state",
            "state",
            "--level",
            "low",
            "--level",
            "high",
            "--json",
            "--min-confidence",
            "0.85",
        ],
    )
    assert result.exit_code == EXIT_CONFIDENCE
    payload = json.loads(result.stdout)
    assert payload["gate"] == {"passed": False, "minimum_confidence": 0.85, "confidence": 0.4}
    assert payload["result"]["request_id"] == "request-1"


def test_named_noul_rejects_confidence_before_api(tmp_path: Path, monkeypatch):
    config = tmp_path / ".pyjev.toml"
    config.write_text("[decision.refund]\ntype='noul'\nquestion='Refund?'\n", encoding="utf-8")
    monkeypatch.setattr(cli, "_run_api", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    result = runner.invoke(
        app,
        ["decide", "refund", "--config", str(config), "--state", "text", "--min-confidence", "0.8"],
    )
    assert result.exit_code == EXIT_USAGE
    assert "only valid" in result.output


def test_decision_management_commands(tmp_path: Path):
    config = tmp_path / ".pyjev.toml"
    config.write_text(
        "[decision.route]\ntype='choice'\nquestion='Route?'\n[decision.route.options]\nbilling='Billing'\nengineering='Technical'\n",
        encoding="utf-8",
    )
    listed = runner.invoke(app, ["decision", "list", "--config", str(config)])
    assert listed.exit_code == 0
    assert "route\tchoice" in listed.stdout

    shown = runner.invoke(app, ["decision", "show", "route", "--config", str(config), "--json"])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["type"] == "choice"

    validated = runner.invoke(app, ["decision", "validate", "--config", str(config)])
    assert validated.exit_code == 0
    assert "Valid" in validated.stdout
    assert "1 decisions" in validated.stdout
