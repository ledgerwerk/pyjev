from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner
from typesafe_sdk import Box

from pyjev import BoxDecision, compile_decision
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


def test_compiled_contract_has_stable_secret_free_identity(tmp_path: Path):
    path = config_file(tmp_path)
    first = compile_decision("route", state="first", config=path)
    second = compile_decision("route", state={"different": True}, config=path)

    first_payload = first.to_dict()
    second_payload = second.to_dict()
    assert first_payload["schema"] == 1
    assert first_payload["decision"]["config"] == ".pyjev.toml"
    assert not Path(first_payload["decision"]["config"]).is_absolute()
    assert len(first.fingerprint) == 64
    assert first.fingerprint == second.fingerprint
    assert first_payload["decision"]["fingerprint"] == first.fingerprint
    assert first_payload["request"]["state"] != second_payload["request"]["state"]


def test_fingerprint_ignores_config_path_but_changes_with_specification(tmp_path: Path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    first_path = config_file(tmp_path / "one")
    second_path = config_file(tmp_path / "two")
    first = compile_decision("route", state="state", config=first_path)
    second = compile_decision("route", state="state", config=second_path)
    assert first.fingerprint == second.fingerprint

    changed = second_path.read_text(encoding="utf-8").replace("Route this ticket", "Route this ticket differently")
    second_path.write_text(changed, encoding="utf-8")
    changed_decision = compile_decision("route", state="state", config=second_path)
    assert changed_decision.fingerprint != first.fingerprint


def test_compile_preserves_structured_choice_and_box_questions(tmp_path: Path) -> None:
    path = tmp_path / ".pyjev.toml"
    path.write_text(
        """[decision.route]
type = "choice"
question = { task = "Route", fields = ["subject", "body"] }

[decision.route.options.billing]
covers = ["refund"]

[decision.route.options.engineering]
covers = ["bug"]

[decision.find-mug]
type = "box"

[decision.find-mug.question]
target = "mug"
image = "photo"
""",
        encoding="utf-8",
    )

    choice = compile_decision("route", state="ticket", config=path)
    assert choice.to_dict()["request"]["questions"]["answer"] == {
        "type": "choice",
        "instructions": {"task": "Route", "fields": ["subject", "body"]},
        "criteria": {"billing": {"covers": ["refund"]}, "engineering": {"covers": ["bug"]}},
    }

    box = compile_decision("find-mug", state={"photo": "local placeholder"}, config=path)
    assert isinstance(box.questions["answer"], Box)
    assert box.to_dict()["request"]["questions"]["answer"] == {
        "type": "box",
        "instructions": {"target": "mug", "image": "photo"},
    }


def test_runtime_decision_validation_accepts_structured_box() -> None:
    from pyjev.compile import validate_runtime_decision

    decision = BoxDecision("find-mug", {"target": "mug", "image": "photo"})
    assert validate_runtime_decision(decision) is decision
