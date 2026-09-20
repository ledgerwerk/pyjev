"""pyjev public API."""

from importlib.metadata import PackageNotFoundError, version

from .client import Jev
from .results import ChoiceResult, NoulResult, ScoreResult

try:
    __version__ = version("pyjev")
except PackageNotFoundError:  # source checkout before installation
    try:
        from ._version import __version__  # type: ignore[import-not-found]
    except ImportError:
        __version__ = "0.0.0"

__all__ = [
    "ChoiceResult",
    "Jev",
    "NoulResult",
    "ScoreResult",
    "__version__",
]
