from __future__ import annotations

from pathlib import Path

import pytest

from pyjev.decisions import (
    ChoiceDecision,
    DecisionConfigError,
    NoulDecision,
    ScoreDecision,
    find_config,
    load_config,
    load_decision,
    load_decisions,
)


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".pyjev.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_all_decision_types_and_models(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
[decision.route]
type = "choice"
question = "Where should this go?"
model = "decision-model"
[decision.route.options]
billing = "Payments"
engineering = "Technical"

[decision.urgent]
type = "score"
question = "How urgent?"
levels = ["normal", "urgent"]

[decision.refund]
type = "noul"
question = "Does the customer want a refund?"
true = "Money returned"
false = "No refund"
""",
    )

    decisions = load_decisions(path)
    assert isinstance(decisions["route"], ChoiceDecision)
    assert decisions["route"].options["billing"] == "Payments"
    assert decisions["route"].model == "decision-model"
    assert isinstance(decisions["urgent"], ScoreDecision)
    assert decisions["urgent"].levels == ("normal", "urgent")
    assert isinstance(decisions["refund"], NoulDecision)
    assert decisions["refund"].true == "Money returned"


def test_explicit_config_and_nearest_parent_discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent = tmp_path / "repo"
    child = parent / "nested"
    child.mkdir(parents=True)
    parent_config = write_config(parent, "[decision.one]\ntype='noul'\nquestion='One'\n")
    child_config = write_config(child, "[decision.two]\ntype='noul'\nquestion='Two'\n")

    assert find_config(start=child) == child_config.resolve()
    assert find_config(start=child / "missing.txt") == child_config.resolve()
    monkeypatch.setenv("PYJEV_CONFIG", str(parent_config))
    assert find_config(start=child) == parent_config.resolve()
    assert load_decision("one", parent_config).name == "one"


def test_invalid_schema_includes_path_name_and_field(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
[decision.route]
type = "choice"
question = "Route?"
unknown = true
[decision.route.options]
only = "One"
""",
    )
    with pytest.raises(DecisionConfigError) as exc_info:
        load_decisions(path)
    message = str(exc_info.value)
    assert str(path) in message
    assert "route" in message
    assert "unknown" in message or "options" in message


@pytest.mark.parametrize(
    ("kind", "field"),
    [("choice", "options"), ("score", "levels")],
)
def test_cardinality_is_validated_locally(tmp_path: Path, kind: str, field: str) -> None:
    values = '["only"]' if kind == "score" else '{ only = "Only" }'
    path = write_config(
        tmp_path,
        f'[decision.bad]\ntype="{kind}"\nquestion="Bad"\n{field}={values}\n',
    )
    with pytest.raises(DecisionConfigError, match=field):
        load_decisions(path)


def test_missing_config_error_mentions_override() -> None:
    with pytest.raises(DecisionConfigError, match=r"\.pyjev\.toml|--config"):
        find_config(start="/")


def test_explicit_schema_one_is_recorded(tmp_path: Path) -> None:
    path = write_config(tmp_path, "[pyjev]\nschema = 1\n[decision.one]\ntype='noul'\nquestion='One'\n")
    loaded = load_config(path)
    assert loaded.schema == 1
    assert loaded.path == path.resolve()


def test_missing_schema_is_implicit_schema_one(tmp_path: Path) -> None:
    path = write_config(tmp_path, "[decision.one]\ntype='noul'\nquestion='One'\n")
    assert load_config(path).schema == 1


@pytest.mark.parametrize(
    "text",
    [
        "[pyjev]\nschema = 2\n[decision.one]\ntype='noul'\nquestion='One'\n",
        "[pyjev]\nschema = '1'\n[decision.one]\ntype='noul'\nquestion='One'\n",
        "[pyjev]\nunknown = true\n[decision.one]\ntype='noul'\nquestion='One'\n",
    ],
)
def test_invalid_schema_is_rejected_before_decisions(tmp_path: Path, text: str) -> None:
    with pytest.raises(DecisionConfigError, match=r"schema|unknown"):
        load_decisions(write_config(tmp_path, text))
