"""Small result wrappers around TypeSafe answer objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NoulResult:
    value: float
    model: str
    usage: dict[str, Any]
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {**self.raw, "model": self.model, "usage": self.usage}


@dataclass(frozen=True, slots=True)
class ChoiceResult:
    value: str
    confidence: float
    probabilities: dict[str, float]
    model: str
    usage: dict[str, Any]
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {**self.raw, "model": self.model, "usage": self.usage}


@dataclass(frozen=True, slots=True)
class ScoreResult:
    value: float
    confidence: float
    probabilities: dict[int, float]
    legend: dict[int, Any]
    model: str
    usage: dict[str, Any]
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {**self.raw, "model": self.model, "usage": self.usage}
