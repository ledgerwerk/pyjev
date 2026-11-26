from __future__ import annotations

from pathlib import Path

import pytest

from pyjev.decisions import (
    BoxDecision,
    ChoiceDecision,
    DecisionConfigError,
    NoulDecision,
    ScoreDecision,
    decision_spec_fingerprint,
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


def test_loads_structured_questions_criteria_and_box(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
[decision.noul]
type = "noul"
question = { task = "Check sender", compare = ["name", "email"] }
true = { definition = "Conflict", examples = ["mismatch"] }
false = { definition = "Consistent" }

[decision.choice]
type = "choice"
question = { task = "Route", fields = ["subject", "body"] }

[decision.choice.options.billing]
covers = ["refund", "invoice"]

[decision.choice.options.engineering]
covers = ["bug"]

[decision.score]
type = "score"
question = { task = "Rate urgency" }
levels = [
  { label = "routine", signals = ["informational"] },
  { label = "critical", signals = ["blocked"] },
]

[decision.box]
type = "box"

[decision.box.question]
target = "mug"
image = "photo"
""",
    )

    decisions = load_decisions(path)
    assert decisions["noul"].question == {"task": "Check sender", "compare": ["name", "email"]}
    assert decisions["noul"].true == {"definition": "Conflict", "examples": ["mismatch"]}
    assert decisions["noul"].false == {"definition": "Consistent"}
    assert decisions["choice"].options == {
        "billing": {"covers": ["refund", "invoice"]},
        "engineering": {"covers": ["bug"]},
    }
    assert decisions["score"].levels == (
        {"label": "routine", "signals": ["informational"]},
        {"label": "critical", "signals": ["blocked"]},
    )
    assert isinstance(decisions["box"], BoxDecision)
    assert decisions["box"].question == {"target": "mug", "image": "photo"}


@pytest.mark.parametrize(
    "question",
    ["42", "{ due = 2026-05-15 }", "{ threshold = nan }"],
)
def test_structured_question_rejects_invalid_roots_and_non_json_values(tmp_path: Path, question: str) -> None:
    config = write_config(tmp_path, f'[decision.bad]\ntype = "noul"\nquestion = {question}\n')
    with pytest.raises(DecisionConfigError, match="JSON-compatible"):
        load_decisions(config)


def test_structured_fingerprint_sorts_objects_but_preserves_arrays(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    changed_dir = tmp_path / "changed"
    first_dir.mkdir()
    second_dir.mkdir()
    changed_dir.mkdir()
    first = write_config(
        first_dir,
        '[decision.structured]\ntype="noul"\nquestion={task="Check", nested={left=1, right=2}, fields=["a", "b"]}\n',
    )
    second = write_config(
        second_dir,
        '[decision.structured]\ntype="noul"\nquestion={fields=["a", "b"], nested={right=2, left=1}, task="Check"}\n',
    )
    changed = write_config(
        changed_dir,
        '[decision.structured]\ntype="noul"\nquestion={task="Check", nested={left=1, right=3}, fields=["a", "b"]}\n',
    )
    assert decision_spec_fingerprint(load_decision("structured", first)) == decision_spec_fingerprint(
        load_decision("structured", second)
    )
    assert decision_spec_fingerprint(load_decision("structured", first)) != decision_spec_fingerprint(
        load_decision("structured", changed)
    )
    array_changed_dir = tmp_path / "array-changed"
    array_changed_dir.mkdir()
    array_changed = write_config(
        array_changed_dir,
        '[decision.structured]\ntype="noul"\nquestion={task="Check", nested={left=1, right=2}, fields=["b", "a"]}\n',
    )
    assert decision_spec_fingerprint(load_decision("structured", first)) != decision_spec_fingerprint(
        load_decision("structured", array_changed)
    )


def test_score_level_order_changes_fingerprint(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = write_config(
        first_dir,
        '[decision.rate]\ntype="score"\nquestion="Rate"\nlevels=[{label="low"}, {label="high"}]\n',
    )
    second = write_config(
        second_dir,
        '[decision.rate]\ntype="score"\nquestion="Rate"\nlevels=[{label="high"}, {label="low"}]\n',
    )
    assert decision_spec_fingerprint(load_decision("rate", first)) != decision_spec_fingerprint(
        load_decision("rate", second)
    )
