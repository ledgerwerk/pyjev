"""pyjev public API."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

from .client import AsyncJev, Jev
from .compile import CompiledDecision, compile_decision
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
    "BundleResult",
    "CompiledDecision",
    "AsyncJev",
    "ChoiceResult",
    "Jev",
    "NoulResult",
    "ScoreResult",
    "compile_decision",
    "__version__",
    "decide",
]
