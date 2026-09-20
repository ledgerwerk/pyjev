from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pyjev import compile_decision
from pyjev.cli import app

runner = CliRunner()


def config_file(tmp_path: Path) -> Path:
    path = tmp_path / ".pyjev.toml"
    path.write_text(
        """[pyjev]
schema = 1

[decision.route]
type = "choice"
question = "Route this ticket"
model = "decision-model"

[decision.route.options]
billing = "Payments"
engineering = "Technical"
""",
        encoding="utf-8",
    )
    return path


def test_compile_is_offline_and_uses_sdk_question_shape(tmp_path: Path, monkeypatch) -> None:
    path = config_file(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    compiled = compile_decision("route", state="checkout fails", config=path, model="call-model")
    payload = compiled.to_dict()
    assert payload["request"]["model"] == "call-model"
    assert payload["request"]["questions"]["answer"] == {
        "type": "choice",
        "instructions": "Route this ticket",
        "criteria": {"billing": "Payments", "engineering": "Technical"},
    }
    assert "TYPESAFE_API_KEY" not in json.dumps(payload)


def test_compile_command_defaults_to_secret_free_json(tmp_path: Path) -> None:
    path = config_file(tmp_path)
    result = runner.invoke(app, ["decision", "compile", "route", "--config", str(path), "--state", "state"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["decision"]["name"] == "route"
    assert payload["request"]["questions"]["answer"]["type"] == "choice"
