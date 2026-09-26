"""Rank candidates and independently judge whether any candidate applies."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Literal

from ..client import AsyncJev, Jev
from ..decisions import BundleDecision, ChoiceDecision, NoulDecision, decision_to_dict
from ..results import BundleResult, ChoiceResult, NoulResult

_NO_CANDIDATE = "__no_candidate__"
_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z")
MAX_CANDIDATES = 254  # One additional closed-set option is reserved for explicit abstention.


@dataclass(frozen=True, slots=True)
class Candidate:
    """A stable candidate identifier and the text considered for semantic relevance."""

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class FindPlan:
    """Credential-free, inspectable request and caller policy for ``find``."""

    query: str
    candidates: tuple[Candidate, ...]
    state: dict[str, Any]
    decision: BundleDecision
    top_k: int
    found_at: float
    absent_below: float

    def to_dict(self) -> dict[str, Any]:
        """Return the exact public state, question specification, and local policy."""
        return {
            "query": self.query,
            "candidates": [{"id": item.id, "text": item.text} for item in self.candidates],
            "state": self.state,
            "decision": decision_to_dict(self.decision),
            "policy": {"top_k": self.top_k, "found_at": self.found_at, "absent_below": self.absent_below},
        }


@dataclass(frozen=True, slots=True)
class FindHit:
    """One candidate ranked by its Choice probability."""

    id: str
    probability: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "probability": self.probability, "text": self.text}


@dataclass(frozen=True, slots=True)
class FindResult:
    """Ranked candidates plus a distinct applicability judgment and its evidence."""

    query: str
    hits: tuple[FindHit, ...]
    exists_probability: float
    exists_verdict: Literal["answered", "partial", "absent"]
    decision: BundleResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "hits": [hit.to_dict() for hit in self.hits],
            "exists_probability": self.exists_probability,
            "exists_verdict": self.exists_verdict,
            "decision": self.decision.to_dict(),
        }


def build_find(
    query: str,
    candidates: list[Candidate] | tuple[Candidate, ...],
    *,
    top_k: int = 5,
    found_at: float = 0.70,
    absent_below: float = 0.35,
    model: str | None = None,
) -> FindPlan:
    """Build a deterministic two-question request without credentials or network I/O.

    ``found_at`` and ``absent_below`` are application policy, not universal correctness
    thresholds. The defaults are starting values only and should be calibrated locally.
    Candidate order is the supplied sequence order and breaks equal-probability ties.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a nonempty string")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    found_threshold = _threshold("found_at", found_at)
    absent_threshold = _threshold("absent_below", absent_below)
    if found_threshold <= absent_threshold:
        raise ValueError("found_at must be greater than absent_below")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError("model must be a nonempty string or None")
    if not isinstance(candidates, (list, tuple)):
        raise TypeError("candidates must be a list or tuple to preserve deterministic ordering")
    items = tuple(candidates)
    if not items:
        raise ValueError("find requires at least one candidate")
    if len(items) > MAX_CANDIDATES:
        raise ValueError(f"find supports at most {MAX_CANDIDATES} candidates")

    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Candidate):
            raise TypeError("candidates must contain Candidate objects")
        if not isinstance(item.id, str) or _ID_PATTERN.fullmatch(item.id) is None:
            raise ValueError("candidate IDs must match [A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
        if item.id == _NO_CANDIDATE:
            raise ValueError(f"candidate ID {item.id!r} is reserved")
        if item.id in seen:
            raise ValueError(f"duplicate candidate ID: {item.id}")
        seen.add(item.id)
        if not isinstance(item.text, str) or not item.text.strip():
            raise ValueError(f"candidate {item.id!r} text must be a nonempty string")

    options: dict[str, Any | None] = {item.id: None for item in items}
    options[_NO_CANDIDATE] = "None of the supplied candidates answers the query."
    state = {"query": query, "candidates": [{"id": item.id, "text": item.text} for item in items]}
    decision = BundleDecision(
        name="find",
        model=model,
        questions={
            "best": ChoiceDecision(
                name="best",
                question=(
                    "Which supplied candidate best answers the query? Select its exact candidate ID, "
                    f"or {_NO_CANDIDATE!r} if none is relevant. Do not invent an ID."
                ),
                options=options,
            ),
            "exists": NoulDecision(
                name="exists",
                question="Does any supplied candidate provide an answer to the query?",
                true="At least one candidate provides an answer.",
                false="No supplied candidate provides an answer.",
            ),
        },
    )
    return FindPlan(
        query=query,
        candidates=items,
        state=state,
        decision=decision,
        top_k=top_k,
        found_at=found_threshold,
        absent_below=absent_threshold,
    )


def interpret_find(plan: FindPlan, decision: BundleResult) -> FindResult:
    """Interpret a synthetic or live bundle result without client or network access."""
    if not isinstance(decision, BundleResult):
        raise TypeError("find interpretation requires a BundleResult")
    try:
        best = decision.answers["best"]
        exists = decision.answers["exists"]
    except KeyError as exc:
        raise ValueError(f"find result is missing answer {exc.args[0]!r}") from exc
    if not isinstance(best, ChoiceResult) or not isinstance(exists, NoulResult):
        raise TypeError("find result has unexpected typed child results")

    input_order = {candidate.id: index for index, candidate in enumerate(plan.candidates)}
    candidate_by_id = {candidate.id: candidate for candidate in plan.candidates}
    probabilities: dict[str, float] = {}
    for candidate_id in input_order:
        probability = best.probabilities.get(candidate_id, 0.0)
        if (
            isinstance(probability, bool)
            or not isinstance(probability, (int, float))
            or not math.isfinite(probability)
            or not 0 <= probability <= 1
        ):
            raise ValueError(f"invalid probability for candidate {candidate_id!r}")
        probabilities[candidate_id] = float(probability)
    ranked_ids = sorted(input_order, key=lambda candidate_id: (-probabilities[candidate_id], input_order[candidate_id]))
    hits = tuple(
        FindHit(id=candidate_id, probability=probabilities[candidate_id], text=candidate_by_id[candidate_id].text)
        for candidate_id in ranked_ids[: plan.top_k]
    )

    exists_probability = exists.value
    if isinstance(exists_probability, bool) or not isinstance(exists_probability, (int, float)):
        raise ValueError("exists probability must be numeric")
    exists_probability = float(exists_probability)
    if not math.isfinite(exists_probability) or not 0 <= exists_probability <= 1:
        raise ValueError("exists probability must be finite and between 0 and 1")
    if exists_probability >= plan.found_at:
        verdict: Literal["answered", "partial", "absent"] = "answered"
    elif exists_probability < plan.absent_below:
        verdict = "absent"
    else:
        verdict = "partial"
    return FindResult(
        query=plan.query,
        hits=hits,
        exists_probability=exists_probability,
        exists_verdict=verdict,
        decision=decision,
    )


def execute_find(jev: Jev, plan: FindPlan) -> FindResult:
    """Execute an already-inspected find plan through the supplied sync client."""
    result = jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, BundleResult):
        raise TypeError("Jev.evaluate returned a non-bundle result for a find plan")
    return interpret_find(plan, result)


async def aexecute_find(jev: AsyncJev, plan: FindPlan) -> FindResult:
    """Execute an already-inspected find plan through the supplied async client."""
    result = await jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, BundleResult):
        raise TypeError("AsyncJev.evaluate returned a non-bundle result for a find plan")
    return interpret_find(plan, result)


def find(
    jev: Jev,
    query: str,
    candidates: list[Candidate] | tuple[Candidate, ...],
    *,
    top_k: int = 5,
    found_at: float = 0.70,
    absent_below: float = 0.35,
    model: str | None = None,
) -> FindResult:
    """Build and execute a rank-plus-existence judgment for one query."""
    return execute_find(
        jev,
        build_find(query, candidates, top_k=top_k, found_at=found_at, absent_below=absent_below, model=model),
    )


async def afind(
    jev: AsyncJev,
    query: str,
    candidates: list[Candidate] | tuple[Candidate, ...],
    *,
    top_k: int = 5,
    found_at: float = 0.70,
    absent_below: float = 0.35,
    model: str | None = None,
) -> FindResult:
    """Async build and execution counterpart to :func:`find`."""
    plan = build_find(query, candidates, top_k=top_k, found_at=found_at, absent_below=absent_below, model=model)
    return await aexecute_find(jev, plan)


def _threshold(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 <= normalized <= 1:
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    return normalized
