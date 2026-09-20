"""pyjev public API."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

from .client import Jev
from .results import ChoiceResult, NoulResult, ScoreResult

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
) -> NoulResult | ChoiceResult | ScoreResult:
    """Evaluate a named decision using a short-lived convenience client."""
    with Jev(api_key=api_key, model=model) as jev:
        return jev.decide(name, state=state, config=config, model=model)


__all__ = [
    "ChoiceResult",
    "Jev",
    "NoulResult",
    "ScoreResult",
    "__version__",
    "decide",
]
