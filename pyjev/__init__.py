"""pyjev public API."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

from .batch import BatchError, BatchRecord, BatchResult, BatchSummary, amap
from .client import AsyncJev, Jev
from .compile import CompiledDecision, compile_decision
from .decisions import BundleDecision, ChoiceDecision, Decision, NoulDecision, ScoreDecision
from .output import OutputPathError, format_json, format_jsonl, format_markdown, pluck, validate_pluck_path
from .pipeline import Accepted, GateEvidence, Rejected
from .results import BundleResult, ChoiceResult, NoulResult, ScoreResult

try:
    from ._version import __version__
except ImportError:  # source checkout without generated setuptools-scm output
    try:
        __version__ = package_version("pyjev")
    except PackageNotFoundError:
        __version__ = "0.0.0"


def decide(
    name: str,
    state: Any,
    *,
    config: str | Path | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> NoulResult | ChoiceResult | ScoreResult | BundleResult:
    """Evaluate a named decision using a short-lived convenience client."""
    with Jev(api_key=api_key, model=model) as jev:
        return jev.decide(name, state=state, config=config, model=model)


__all__ = [
    "Accepted",
    "amap",
    "BatchError",
    "BatchRecord",
    "BatchResult",
    "BatchSummary",
    "GateEvidence",
    "Rejected",
    "OutputPathError",
    "format_json",
    "format_jsonl",
    "format_markdown",
    "pluck",
    "validate_pluck_path",
    "BundleResult",
    "BundleDecision",
    "ChoiceDecision",
    "Decision",
    "CompiledDecision",
    "AsyncJev",
    "ChoiceResult",
    "Jev",
    "NoulResult",
    "NoulDecision",
    "ScoreResult",
    "ScoreDecision",
    "compile_decision",
    "__version__",
    "decide",
]
