"""Small result wrappers around TypeSafe answer objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeAlias, TypedDict


@dataclass(frozen=True, slots=True)
class NoulResult:
    """A Noul probability and response metadata."""

    value: float
    model: str
    usage: dict[str, Any]
    raw: dict[str, Any]
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the raw answer with shared response metadata."""
        return {**self.raw, "model": self.model, "usage": self.usage, "request_id": self.request_id}


@dataclass(frozen=True, slots=True)
class ChoiceResult:
    """A selected Choice label, confidence, distribution, and metadata."""

    value: str
    confidence: float
    probabilities: dict[str, float]
    model: str
    usage: dict[str, Any]
    raw: dict[str, Any]
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the raw answer with shared response metadata."""
        return {**self.raw, "model": self.model, "usage": self.usage, "request_id": self.request_id}


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """A fractional Score, confidence, distribution, legend, and metadata."""

    value: float
    confidence: float
    probabilities: dict[int, float]
    legend: dict[int, Any]
    model: str
    usage: dict[str, Any]
    raw: dict[str, Any]
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the raw answer with shared response metadata."""
        return {**self.raw, "model": self.model, "usage": self.usage, "request_id": self.request_id}


class BoxCoordinates(TypedDict):
    """Normalized top, bottom, left, and right image coordinates."""

    top: float
    bottom: float
    left: float
    right: float


@dataclass(frozen=True, slots=True)
class BoxResult:
    """A normalized image box, confidence, and response metadata."""

    value: BoxCoordinates
    confidence: float | None
    model: str
    usage: dict[str, Any]
    raw: dict[str, Any]
    request_id: str | None = None

    @property
    def box(self) -> BoxCoordinates:
        """Return the normalized box coordinates."""
        return self.value

    def to_dict(self) -> dict[str, Any]:
        """Return the raw answer with shared response metadata."""
        return {**self.raw, "model": self.model, "usage": self.usage, "request_id": self.request_id}


PrimitiveResult: TypeAlias = NoulResult | ChoiceResult | ScoreResult | BoxResult


@dataclass(frozen=True, slots=True)
class BundleResult:
    """Uncertainty-preserving results for several typed questions in one request."""

    answers: dict[str, PrimitiveResult]
    model: str
    usage: dict[str, Any]
    raw: dict[str, Any]
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible bundle envelope."""
        return {
            "answers": {name: answer.to_dict() for name, answer in self.answers.items()},
            "model": self.model,
            "usage": self.usage,
            "raw": self.raw,
            "request_id": self.request_id,
        }
