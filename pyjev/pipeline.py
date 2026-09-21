"""Local composition stages for already-evaluated pyjev results."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeAlias, TypeVar

from .results import BundleResult, ChoiceResult, NoulResult, PrimitiveResult, ScoreResult

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
ValueT = TypeVar("ValueT")


class PipelineError(ValueError):
    """Base class for invalid local result-pipeline operations."""


class PipelineTypeError(PipelineError, TypeError):
    """A stage received an incompatible pyjev result type."""


class PipelineLookupError(PipelineError, KeyError):
    """A requested bundle answer does not exist."""


@dataclass(frozen=True, slots=True)
class GateEvidence:
    """The signal and threshold used by a local gate."""

    signal: Literal["confidence", "probability"]
    observed: float
    comparator: Literal["at_least", "at_most"]
    threshold: float


@dataclass(frozen=True, slots=True)
class Accepted(Generic[ValueT]):
    """A result value that satisfied an application policy gate."""

    value: ValueT
    result: PrimitiveResult
    gate: GateEvidence
    passed: Literal[True] = True


@dataclass(frozen=True, slots=True)
class Rejected:
    """A valid result that did not satisfy an application policy gate."""

    result: PrimitiveResult
    gate: GateEvidence
    passed: Literal[False] = False


GateOutcome: TypeAlias = Accepted[Any] | Rejected


class PipeStage(Generic[InputT, OutputT]):
    """A local stage that can consume one pipeline value."""

    def apply(self, value: InputT) -> OutputT:
        raise NotImplementedError

    def __ror__(self, value: InputT) -> OutputT:
        return self.apply(value)

    def __or__(self, other: PipeStage[Any, Any]) -> Pipe:
        if not isinstance(other, PipeStage):
            raise TypeError("pipeline stages can only be composed with another PipeStage")
        if isinstance(other, Pipe):
            return Pipe((self, *other.stages))
        return Pipe((self, other))


@dataclass(frozen=True, slots=True)
class Pipe(PipeStage[Any, Any]):
    """An immutable left-to-right composition of local pipeline stages."""

    stages: tuple[PipeStage[Any, Any], ...]

    def apply(self, value: Any) -> Any:
        for stage in self.stages:
            value = stage.apply(value)
        return value

    def __or__(self, other: PipeStage[Any, Any]) -> Pipe:
        if not isinstance(other, PipeStage):
            raise TypeError("pipeline stages can only be composed with another PipeStage")
        if isinstance(other, Pipe):
            return Pipe((*self.stages, *other.stages))
        return Pipe((*self.stages, other))


@dataclass(frozen=True, slots=True)
class AnswerStage(PipeStage[BundleResult, PrimitiveResult]):
    """Select one existing primitive result from a bundle."""

    name: str

    def apply(self, value: BundleResult) -> PrimitiveResult:
        if not isinstance(value, BundleResult):
            raise PipelineTypeError(
                f"answer({self.name!r}) expected BundleResult, got {type(value).__name__}"
            )
        try:
            return value.answers[self.name]
        except KeyError as error:
            available = ", ".join(sorted(value.answers)) or "<none>"
            raise PipelineLookupError(
                f"unknown bundle answer {self.name!r}; available answers: {available}"
            ) from error


@dataclass(frozen=True, slots=True)
class ConfidenceGateStage(PipeStage[ChoiceResult | ScoreResult, GateOutcome]):
    """Gate a Choice or Score result using its Jev confidence signal."""

    minimum: float

    def apply(self, value: ChoiceResult | ScoreResult) -> GateOutcome:
        if not isinstance(value, (ChoiceResult, ScoreResult)):
            raise PipelineTypeError(
                "require_confidence expected ChoiceResult or ScoreResult, "
                f"got {type(value).__name__}"
            )
        gate = GateEvidence(
            signal="confidence",
            observed=value.confidence,
            comparator="at_least",
            threshold=self.minimum,
        )
        if value.confidence >= self.minimum:
            return Accepted(value=value.value, result=value, gate=gate)
        return Rejected(result=value, gate=gate)


@dataclass(frozen=True, slots=True)
class ProbabilityGateStage(PipeStage[NoulResult, GateOutcome]):
    """Gate a Noul result using its probability-of-true value."""

    comparator: Literal["at_least", "at_most"]
    threshold: float

    def apply(self, value: NoulResult) -> GateOutcome:
        if not isinstance(value, NoulResult):
            raise PipelineTypeError(
                "require_probability expected NoulResult, "
                f"got {type(value).__name__}"
            )
        gate = GateEvidence(
            signal="probability",
            observed=value.value,
            comparator=self.comparator,
            threshold=self.threshold,
        )
        passed = (
            value.value >= self.threshold
            if self.comparator == "at_least"
            else value.value <= self.threshold
        )
        if passed:
            return Accepted(value=value.value, result=value, gate=gate)
        return Rejected(result=value, gate=gate)


def _validate_threshold(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite value between 0 and 1")
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return float(value)


def answer(name: str) -> AnswerStage:
    """Create a stage selecting a named child from a BundleResult."""
    if not isinstance(name, str) or not name:
        raise ValueError("answer name must be a non-empty string")
    return AnswerStage(name=name)


def require_confidence(minimum: float) -> ConfidenceGateStage:
    """Create an inclusive confidence gate for Choice or Score results."""
    return ConfidenceGateStage(minimum=_validate_threshold(minimum, "confidence threshold"))


def require_probability(
    *, at_least: float | None = None, at_most: float | None = None
) -> ProbabilityGateStage:
    """Create an inclusive lower or upper probability gate for Noul results."""
    if (at_least is None) == (at_most is None):
        raise ValueError("require_probability requires exactly one of at_least or at_most")
    if at_least is not None:
        return ProbabilityGateStage(
            comparator="at_least",
            threshold=_validate_threshold(at_least, "probability threshold"),
        )
    return ProbabilityGateStage(
        comparator="at_most",
        threshold=_validate_threshold(at_most, "probability threshold"),
    )
