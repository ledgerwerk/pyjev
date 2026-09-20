"""Lint Python functions with a named bundle of plain-English Jev rules."""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyjev import AsyncJev, BundleResult, NoulResult

CONFIG = Path(__file__).with_name(".pyjev.toml")
DECISION = "semantic-lint"
DEFAULT_THRESHOLD = 0.70
DEFAULT_MAX_CONCURRENCY = 8
SKIPPED_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "build",
        "dist",
        ".tox",
        ".nox",
    }
)


@dataclass(frozen=True, slots=True)
class FunctionUnit:
    path: str
    qualname: str
    line: int
    source: str


@dataclass(frozen=True, slots=True)
class RuleJudgment:
    rule: str
    probability: float


@dataclass(frozen=True, slots=True)
class FunctionReport:
    unit: FunctionUnit
    judgments: tuple[RuleJudgment, ...]
    model: str
    usage: dict[str, Any]
    request_id: str | None


@dataclass(frozen=True, slots=True)
class RunReport:
    target: str
    decision: str
    threshold: float
    elapsed_seconds: float
    functions: tuple[FunctionReport, ...]
    usage: dict[str, Any]
    models: tuple[str, ...]

    @property
    def function_count(self) -> int:
        return len(self.functions)

    @property
    def rule_count(self) -> int:
        return len(self.functions[0].judgments) if self.functions else 0

    @property
    def judgment_count(self) -> int:
        return self.function_count * self.rule_count

    @property
    def request_count(self) -> int:
        return self.function_count

    def findings(self) -> list[FunctionReport]:
        return [
            report
            for report in self.functions
            if any(judgment.probability >= self.threshold for judgment in report.judgments)
        ]


def discover_python_files(target: Path) -> list[Path]:
    """Return deterministic Python files for a file or directory target."""
    if not target.exists():
        raise ValueError(f"target does not exist: {target}")
    if target.is_file():
        if target.suffix != ".py":
            raise ValueError(f"target file is not a Python file: {target}")
        return [target]
    if not target.is_dir():
        raise ValueError(f"target is not a file or directory: {target}")

    files = [
        path
        for path in target.rglob("*.py")
        if not any(part in SKIPPED_DIRECTORIES for part in path.relative_to(target).parts[:-1])
    ]
    return sorted(files, key=lambda path: path.as_posix())


class _FunctionVisitor:
    def __init__(self, path: Path, source: str) -> None:
        self.path = path
        self.source_lines = source.splitlines(keepends=True)
        self.scopes: list[str] = []
        self.units: list[FunctionUnit] = []

    def visit_class(self, node: Any) -> None:
        self.scopes.append(node.name)
        for child in ast.iter_child_nodes(node):
            self.visit(child)
        self.scopes.pop()

    def visit_function(self, node: Any) -> None:
        self.scopes.append(node.name)
        qualname = ".".join(self.scopes)
        decorator_lines = [decorator.lineno for decorator in node.decorator_list]
        start_line = min([node.lineno, *decorator_lines])
        end_line = node.end_lineno
        source = "".join(self.source_lines[start_line - 1 : end_line])
        self.units.append(FunctionUnit(self.path.as_posix(), qualname, start_line, source))
        for child in ast.iter_child_nodes(node):
            self.visit(child)
        self.scopes.pop()

    def visit(self, node: Any) -> None:
        if isinstance(node, ast.ClassDef):
            self.visit_class(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.visit_function(node)
        else:
            for child in ast.iter_child_nodes(node):
                self.visit(child)


def extract_functions(path: Path) -> list[FunctionUnit]:
    """Parse one Python file and return its functions in source order."""
    source = path.read_text(encoding="utf-8")

    tree = ast.parse(source, filename=str(path))
    visitor = _FunctionVisitor(path, source)
    for node in tree.body:
        visitor.visit(node)
    return visitor.units


def extract_target(target: str | Path) -> list[FunctionUnit]:
    """Discover and extract all functions from a target."""
    path = Path(target)
    units: list[FunctionUnit] = []
    for python_file in discover_python_files(path):
        units.extend(extract_functions(python_file))
    return sorted(units, key=lambda unit: (unit.path, unit.line, unit.qualname))


def state_for(unit: FunctionUnit) -> dict[str, Any]:
    return {
        "language": "python",
        "path": unit.path,
        "qualified_name": unit.qualname,
        "start_line": unit.line,
        "source": unit.source,
    }


async def lint_one(
    jev: Any,
    unit: FunctionUnit,
    *,
    config: Path,
    decision: str,
    semaphore: asyncio.Semaphore,
) -> FunctionReport:
    async with semaphore:
        result = await jev.decide(decision, state=state_for(unit), config=config)
    if not isinstance(result, BundleResult):
        raise TypeError(f"{decision!r} must be a bundle, got {type(result).__name__}")
    if not result.answers:
        raise ValueError(f"{decision!r} bundle has no rules")

    judgments: list[RuleJudgment] = []
    for rule, answer in result.answers.items():
        if not isinstance(answer, NoulResult):
            raise TypeError(f"{decision!r} rule {rule!r} must be NoulResult, got {type(answer).__name__}")
        judgments.append(RuleJudgment(rule=rule, probability=answer.value))
    return FunctionReport(
        unit=unit,
        judgments=tuple(judgments),
        model=result.model,
        usage=dict(result.usage),
        request_id=result.request_id,
    )


def _sum_usage(reports: Iterable[FunctionReport]) -> dict[str, Any]:
    aggregate: dict[str, Any] = {}
    for report in reports:
        for key, value in report.usage.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                aggregate[key] = aggregate.get(key, 0) + value
            elif key not in aggregate:
                aggregate[key] = value
    return aggregate


async def lint_all(
    units: Iterable[FunctionUnit],
    *,
    config: Path,
    decision: str = DECISION,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    jev_factory: Callable[[], Any] = AsyncJev,
    target: str = "",
    threshold: float = DEFAULT_THRESHOLD,
) -> RunReport:
    if max_concurrency < 1:
        raise ValueError("max concurrency must be at least 1")
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")

    ordered_units = sorted(units, key=lambda unit: (unit.path, unit.line, unit.qualname))
    semaphore = asyncio.Semaphore(max_concurrency)
    started = time.perf_counter()
    async with jev_factory() as jev:
        reports = await asyncio.gather(
            *[
                lint_one(
                    jev,
                    unit,
                    config=config,
                    decision=decision,
                    semaphore=semaphore,
                )
                for unit in ordered_units
            ]
        )
    elapsed = time.perf_counter() - started
    sorted_reports = tuple(
        sorted(reports, key=lambda report: (report.unit.path, report.unit.line, report.unit.qualname))
    )
    return RunReport(
        target=target,
        decision=decision,
        threshold=threshold,
        elapsed_seconds=elapsed,
        functions=sorted_reports,
        usage=_sum_usage(sorted_reports),
        models=tuple(sorted({report.model for report in sorted_reports})),
    )


def _display_judgments(report: FunctionReport, threshold: float, show_all: bool) -> list[RuleJudgment]:
    judgments = sorted(report.judgments, key=lambda judgment: judgment.probability, reverse=True)
    if show_all:
        return judgments
    return [judgment for judgment in judgments if judgment.probability >= threshold]


def human_report(report: RunReport, *, show_all: bool = False, max_concurrency: int = DEFAULT_MAX_CONCURRENCY) -> str:
    lines = [
        "=== Plain-English Semantic Linter ===",
        f"Jev will judge each Python function against {report.rule_count} semantic rules.",
        "Python owns parsing and function boundaries; Jev owns the fuzzy judgments.",
        "The selected function source is sent to the configured Jev API. "
        "Do not run the example on code you are not permitted to send to that service.",
        "",
        f"target:            {report.target}",
        f"functions:         {report.function_count}",
        f"rules:             {report.rule_count}",
        f"judgments:         {report.judgment_count}",
        f"requests:          {report.request_count}",
        f"max concurrency:   {max_concurrency}",
        f"report threshold:  {report.threshold:.2f}  (demo application policy)",
        "",
    ]

    displayed = 0
    for function in report.functions:
        judgments = _display_judgments(function, report.threshold, show_all)
        if not judgments:
            continue
        displayed += 1
        lines.append(f"{function.unit.path}:{function.unit.line}  {function.unit.qualname}")
        for judgment in judgments:
            lines.append(f"  {judgment.probability:5.2f}  {judgment.rule}")
        lines.append("")
    if not show_all and not displayed:
        lines.append(f"No findings at the {report.threshold:.2f} reporting threshold.")
        lines.append("")

    lines.extend(
        [
            "Summary",
            f"  functions with findings: {len(report.findings())} / {report.function_count}",
            f"  judgments:              {report.judgment_count}",
            f"  requests:               {report.request_count}",
            f"  input tokens:           {report.usage.get('input_tokens', 'not reported')}",
            f"  output tokens:          {report.usage.get('output_tokens', 'not reported')}",
            f"  elapsed:                {report.elapsed_seconds:.2f}s on this run",
            f"  model(s):               {', '.join(report.models) if report.models else 'not reported'}",
        ]
    )
    return "\n".join(lines)


def json_report(report: RunReport) -> dict[str, Any]:
    return {
        "target": report.target,
        "decision": report.decision,
        "threshold": report.threshold,
        "function_count": report.function_count,
        "rule_count": report.rule_count,
        "judgment_count": report.judgment_count,
        "request_count": report.request_count,
        "elapsed_seconds": report.elapsed_seconds,
        "usage": report.usage,
        "models": list(report.models),
        "functions": [
            {
                "path": function.unit.path,
                "qualname": function.unit.qualname,
                "line": function.unit.line,
                "request_id": function.request_id,
                "model": function.model,
                "usage": function.usage,
                "judgments": {judgment.rule: judgment.probability for judgment in function.judgments},
            }
            for function in report.functions
        ],
    }


def _threshold(value: str) -> float:
    try:
        threshold = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("threshold must be a number between 0 and 1") from exc
    if not 0 <= threshold <= 1:
        raise argparse.ArgumentTypeError("threshold must be between 0 and 1")
    return threshold


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Judge Python functions against a named bundle of plain-English semantic rules.",
        epilog=(
            "The reporting threshold is application policy, not a Jev correctness guarantee. "
            "Source code is sent to the configured Jev API."
        ),
    )
    parser.add_argument("target", help="Python file or directory to inspect")
    parser.add_argument(
        "--threshold",
        type=_threshold,
        default=DEFAULT_THRESHOLD,
        help="Noul probability at which a rule is shown (default: 0.70)",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=DEFAULT_MAX_CONCURRENCY,
        help="maximum in-flight Jev requests (default: 8)",
    )
    parser.add_argument("--show-all", action="store_true", help="print every rule probability instead of only findings")
    parser.add_argument("--json", action="store_true", help="emit one structured JSON report")
    parser.add_argument("--config", type=Path, default=CONFIG, help="override the named-decision config")
    parser.add_argument("--decision", default=DECISION, help=f"named decision to use (default: {DECISION})")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="exit 1 when any rule meets the reporting threshold",
    )
    return parser.parse_args(argv)


def _syntax_error_message(error: SyntaxError) -> str:
    location = error.filename or "<input>"
    if error.lineno is not None:
        location += f":{error.lineno}"
    return f"{location}: syntax error: {error.msg}"


async def async_main(args: argparse.Namespace, *, jev_factory: Callable[[], Any] = AsyncJev) -> int:
    if args.max_concurrency < 1:
        raise ValueError("max concurrency must be at least 1")
    units = extract_target(args.target)
    report = await lint_all(
        units,
        config=args.config,
        decision=args.decision,
        max_concurrency=args.max_concurrency,
        jev_factory=jev_factory,
        target=str(args.target),
        threshold=args.threshold,
    )
    if args.json:
        print(json.dumps(json_report(report), indent=2, sort_keys=True))
    else:
        print(human_report(report, show_all=args.show_all, max_concurrency=args.max_concurrency))
    return 1 if args.fail_on_findings and report.findings() else 0


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(async_main(parse_args(argv)))
    except SyntaxError as exc:
        print(f"error: {_syntax_error_message(exc)}", file=sys.stderr)
        return 2
    except (OSError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
