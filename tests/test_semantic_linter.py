from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from examples.semantic_linter import (
    DEFAULT_THRESHOLD,
    FunctionUnit,
    async_main,
    extract_functions,
    extract_target,
    human_report,
    json_report,
    lint_all,
    parse_args,
    state_for,
)
from pyjev import BundleResult, NoulResult
from pyjev.decisions import BundleDecision, NoulDecision, load_decision

CONFIG = Path(__file__).parents[1] / "examples" / ".pyjev.toml"
RULES = tuple(load_decision("semantic-lint", CONFIG).questions)


class FakeJev:
    def __init__(self, *, probabilities: dict[str, float] | None = None, delay: bool = False) -> None:
        self.probabilities = probabilities or {rule: 0.1 for rule in RULES}
        self.delay = delay
        self.calls: list[tuple[str, dict[str, Any], Path]] = []
        self.active = 0
        self.peak_active = 0

    async def __aenter__(self) -> FakeJev:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def decide(self, decision: str, *, state: dict[str, Any], config: Path) -> BundleResult:
        assert decision == "semantic-lint"
        self.calls.append((decision, state, config))
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        if self.delay:
            await asyncio.sleep(0 if state["start_line"] % 2 else 0.001)
        answers = {
            rule: NoulResult(
                value=self.probabilities.get(rule, 0.1),
                model="fake-model",
                usage={"input_tokens": 100, "output_tokens": 10},
                raw={"noul": self.probabilities.get(rule, 0.1)},
            )
            for rule in RULES
        }
        self.active -= 1
        return BundleResult(
            answers=answers,
            model="fake-model",
            usage={"input_tokens": 100, "output_tokens": 10},
            raw={},
            request_id=f"request-{len(self.calls)}",
        )


def factory_for(fake: FakeJev):
    return lambda: fake


def test_extracts_decorated_async_methods_and_nested_functions(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text(
        (
            "@decorator\n"
            "def decorated(value):\n"
            "    return value\n\n"
            "async def fetch():\n"
            "    return 1\n\n"
            "class Service:\n"
            "    @classmethod\n"
            "    def build(cls):\n"
            "        def nested():\n"
            "            return cls\n"
            "        return nested\n"
        ),
        encoding="utf-8",
    )

    units = extract_functions(path)

    assert [unit.qualname for unit in units] == [
        "decorated",
        "fetch",
        "Service.build",
        "Service.build.nested",
    ]
    assert units[0].line == 1
    assert "@decorator" in units[0].source
    assert units[1].line == 5
    assert units[2].line == 9
    assert units[3].line == 11


def test_syntax_failure_happens_before_jev(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    path.write_text("def broken(:\n    pass\n", encoding="utf-8")
    fake = FakeJev()

    with pytest.raises(SyntaxError):
        extract_target(path)
    assert fake.calls == []


def test_config_contains_exactly_fourteen_noul_rules() -> None:
    decision = load_decision("semantic-lint", CONFIG)

    assert isinstance(decision, BundleDecision)
    assert len(decision.questions) == 14
    assert all(isinstance(question, NoulDecision) for question in decision.questions.values())
    assert [decision.questions[name].question for name in RULES[:3]] == [
        "This function swallows errors.",
        "This function has a hidden side effect.",
        "This function does too many jobs.",
    ]


def test_one_bundle_request_per_function_and_structured_state(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text("def first():\n    return 1\n\ndef second():\n    return 2\n", encoding="utf-8")
    units = extract_target(path)
    fake = FakeJev()

    report = asyncio.run(lint_all(units, config=CONFIG, jev_factory=factory_for(fake), target=str(path)))

    assert len(fake.calls) == len(units) == report.request_count
    for decision, state, config in fake.calls:
        assert decision == "semantic-lint"
        assert config == CONFIG
        assert set(state) == {"language", "path", "qualified_name", "start_line", "source"}
        assert state["language"] == "python"


def test_all_bundle_children_are_consumed_and_counts_are_arithmetic() -> None:
    units = [
        FunctionUnit("sample.py", "first", 1, "def first(): pass"),
        FunctionUnit("sample.py", "second", 2, "def second(): pass"),
        FunctionUnit("sample.py", "third", 3, "def third(): pass"),
    ]
    fake = FakeJev()

    report = asyncio.run(lint_all(units, config=CONFIG, jev_factory=factory_for(fake), target="sample.py"))

    assert report.function_count == 3
    assert report.rule_count == 14
    assert report.judgment_count == 42
    assert report.request_count == 3
    assert all(len(function.judgments) == 14 for function in report.functions)


def test_usage_is_aggregated_once_per_request() -> None:
    units = [FunctionUnit("sample.py", name, index, "def f(): pass") for index, name in enumerate("abc", 1)]
    fake = FakeJev()

    report = asyncio.run(lint_all(units, config=CONFIG, jev_factory=factory_for(fake)))

    assert report.usage == {"input_tokens": 300, "output_tokens": 30}


def test_threshold_changes_display_but_not_json_or_judgments() -> None:
    units = [FunctionUnit("sample.py", "first", 1, "def first(): pass")]
    fake = FakeJev(probabilities={RULES[0]: 0.8, **{rule: 0.2 for rule in RULES[1:]}})
    report = asyncio.run(lint_all(units, config=CONFIG, jev_factory=factory_for(fake), threshold=DEFAULT_THRESHOLD))

    human = human_report(report)
    show_all = human_report(report, show_all=True)
    payload = json_report(report)
    assert RULES[0] in human
    assert RULES[1] not in human
    assert all(rule in show_all for rule in RULES)
    assert set(payload["functions"][0]["judgments"]) == set(RULES)
    assert len(report.findings()) == 1
    assert parse_args(["sample.py", "--threshold", "0.8"]).threshold == 0.8


def test_fail_on_findings_only_changes_exit_policy(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text("def sample():\n    return 1\n", encoding="utf-8")
    finding_fake = FakeJev(probabilities={rule: 0.8 for rule in RULES})
    finding_args = parse_args([str(path), "--json", "--fail-on-findings"])
    assert asyncio.run(async_main(finding_args, jev_factory=factory_for(finding_fake))) == 1

    quiet_fake = FakeJev()
    quiet_args = parse_args([str(path), "--json", "--fail-on-findings"])
    assert asyncio.run(async_main(quiet_args, jev_factory=factory_for(quiet_fake))) == 0


def test_concurrency_is_bounded_and_results_are_stably_ordered() -> None:
    units = [
        FunctionUnit("z.py", "z", 3, "def z(): pass"),
        FunctionUnit("a.py", "a", 2, "def a(): pass"),
        FunctionUnit("m.py", "m", 1, "def m(): pass"),
        FunctionUnit("b.py", "b", 4, "def b(): pass"),
    ]
    fake = FakeJev(delay=True)

    report = asyncio.run(lint_all(units, config=CONFIG, jev_factory=factory_for(fake), max_concurrency=2))

    assert fake.peak_active <= 2
    assert [(function.unit.path, function.unit.line) for function in report.functions] == [
        ("a.py", 2),
        ("b.py", 4),
        ("m.py", 1),
        ("z.py", 3),
    ]


def test_state_for_is_explicit() -> None:
    unit = FunctionUnit("sample.py", "Thing.work", 12, "def work(): pass")
    assert state_for(unit) == {
        "language": "python",
        "path": "sample.py",
        "qualified_name": "Thing.work",
        "start_line": 12,
        "source": "def work(): pass",
    }
