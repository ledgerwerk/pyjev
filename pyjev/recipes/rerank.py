"""Independent per-candidate relevance judgments with deterministic chunked ordering."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..client import AsyncJev, Jev
from ..decisions import BundleDecision, NoulDecision, decision_to_dict
from ..results import BundleResult, NoulResult
from ._common import probability, threshold, validate_id, validate_model

DEFAULT_CHUNK_SIZE = 64
MAX_CHUNK_SIZE = 64
MAX_CANDIDATES = 4096


@dataclass(frozen=True, slots=True)
class RerankCandidate:
    """Stable candidate identifier and text judged independently for relevance."""

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class RerankChunk:
    """One bounded bundle request and its stable candidate-to-question mapping."""

    index: int
    candidates: tuple[RerankCandidate, ...]
    state: dict[str, Any]
    decision: BundleDecision
    candidate_keys: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "candidate_ids": [candidate.id for candidate in self.candidates],
            "state": self.state,
            "decision": decision_to_dict(self.decision),
            "candidate_keys": self.candidate_keys,
        }


@dataclass(frozen=True, slots=True)
class RerankPlan:
    """Inspect-before-execute plan; large inputs split into deterministic fixed chunks."""

    query: str
    candidates: tuple[RerankCandidate, ...]
    chunks: tuple[RerankChunk, ...]
    min_relevance: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "candidates": [{"id": candidate.id, "text": candidate.text} for candidate in self.candidates],
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "policy": {"min_relevance": self.min_relevance},
        }


@dataclass(frozen=True, slots=True)
class RerankItem:
    """One independent relevance result in original input order."""

    id: str
    text: str
    probability: float
    relevant: bool | None
    decision: NoulResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "probability": self.probability,
            "relevant": self.relevant,
            "decision": self.decision.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class RerankResult:
    """Stable ranked candidates and every underlying chunk result."""

    query: str
    results: tuple[RerankItem, ...]
    ranked: tuple[RerankItem, ...]
    decisions: tuple[BundleResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "results": [item.to_dict() for item in self.results],
            "ranked": [item.to_dict() for item in self.ranked],
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


def build_rerank(
    query: str,
    candidates: Sequence[RerankCandidate],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    min_relevance: float | None = None,
    model: str | None = None,
) -> RerankPlan:
    """Build independent Noul judgments, splitting large input deterministically.

    Unlike :func:`pyjev.recipes.find`, candidates do not compete in one Choice distribution;
    any number may be relevant. A chunk is executed as one bundle request. Thresholding is
    optional caller policy, and no candidate is silently dropped.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a nonempty string")
    validate_model(model)
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or not 1 <= chunk_size <= MAX_CHUNK_SIZE:
        raise ValueError(f"chunk_size must be between 1 and {MAX_CHUNK_SIZE}")
    if min_relevance is not None:
        min_relevance = threshold(min_relevance, "min_relevance")
    items = _normalize_candidates(candidates)
    if not items:
        raise ValueError("rerank requires at least one candidate")
    if len(items) > MAX_CANDIDATES:
        raise ValueError(f"rerank supports at most {MAX_CANDIDATES} candidates")

    chunks: list[RerankChunk] = []
    for chunk_index, start in enumerate(range(0, len(items), chunk_size)):
        chunk_candidates = items[start : start + chunk_size]
        questions: dict[str, NoulDecision] = {}
        candidate_keys: dict[str, str] = {}
        for offset, candidate in enumerate(chunk_candidates):
            key = f"relevant_{start + offset:04d}"
            candidate_keys[candidate.id] = key
            questions[key] = NoulDecision(
                name=key,
                question=f"Is candidate {candidate.id!r} relevant to the query? Query: {query}",
                true="The candidate is relevant and useful for this query.",
                false="The candidate is not relevant to this query.",
            )
        state = {
            "query": query,
            "candidates": [{"id": candidate.id, "text": candidate.text} for candidate in chunk_candidates],
        }
        chunks.append(
            RerankChunk(
                chunk_index,
                chunk_candidates,
                state,
                BundleDecision(name=f"rerank_{chunk_index:04d}", questions=questions, model=model),
                candidate_keys,
            )
        )
    return RerankPlan(query, items, tuple(chunks), min_relevance)


def interpret_rerank(plan: RerankPlan, decisions: Sequence[BundleResult]) -> RerankResult:
    """Interpret synthetic or live chunk results using independent probabilities."""
    if not isinstance(decisions, (list, tuple)) or len(decisions) != len(plan.chunks):
        raise ValueError(f"rerank requires exactly {len(plan.chunks)} chunk results")
    by_id: dict[str, RerankItem] = {}
    for chunk, result in zip(plan.chunks, decisions, strict=True):
        if not isinstance(result, BundleResult):
            raise TypeError(f"rerank chunk {chunk.index} requires a BundleResult")
        for candidate in chunk.candidates:
            key = chunk.candidate_keys[candidate.id]
            answer = result.answers.get(key)
            if not isinstance(answer, NoulResult):
                raise ValueError(f"rerank result is missing Noul answer {key!r}")
            relevance = probability(answer.value, f"relevance probability for {candidate.id!r}")
            relevant = relevance >= plan.min_relevance if plan.min_relevance is not None else None
            by_id[candidate.id] = RerankItem(candidate.id, candidate.text, relevance, relevant, answer)
    original = tuple(by_id[candidate.id] for candidate in plan.candidates)
    input_order = {candidate.id: index for index, candidate in enumerate(plan.candidates)}
    ranked = tuple(sorted(original, key=lambda item: (-item.probability, input_order[item.id])))
    return RerankResult(plan.query, original, ranked, tuple(decisions))


def execute_rerank(jev: Jev, plan: RerankPlan) -> RerankResult:
    results: list[BundleResult] = []
    for chunk in plan.chunks:
        result = jev.evaluate(chunk.decision, state=chunk.state)
        if not isinstance(result, BundleResult):
            raise TypeError(f"Jev.evaluate returned a non-bundle result for rerank chunk {chunk.index}")
        results.append(result)
    return interpret_rerank(plan, results)


async def aexecute_rerank(jev: AsyncJev, plan: RerankPlan) -> RerankResult:
    results: list[BundleResult] = []
    for chunk in plan.chunks:
        result = await jev.evaluate(chunk.decision, state=chunk.state)
        if not isinstance(result, BundleResult):
            raise TypeError(f"AsyncJev.evaluate returned a non-bundle result for rerank chunk {chunk.index}")
        results.append(result)
    return interpret_rerank(plan, results)


def rerank(
    jev: Jev,
    query: str,
    candidates: Sequence[RerankCandidate],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    min_relevance: float | None = None,
    model: str | None = None,
) -> RerankResult:
    """Build and execute deterministic chunks through the supplied sync client."""
    plan = build_rerank(
        query,
        candidates,
        chunk_size=chunk_size,
        min_relevance=min_relevance,
        model=model,
    )
    return execute_rerank(jev, plan)


async def arerank(
    jev: AsyncJev,
    query: str,
    candidates: Sequence[RerankCandidate],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    min_relevance: float | None = None,
    model: str | None = None,
) -> RerankResult:
    """Native-async counterpart to :func:`rerank`, with sequential chunk dispatch."""
    plan = build_rerank(
        query,
        candidates,
        chunk_size=chunk_size,
        min_relevance=min_relevance,
        model=model,
    )
    return await aexecute_rerank(jev, plan)


def _normalize_candidates(candidates: Sequence[RerankCandidate]) -> tuple[RerankCandidate, ...]:
    if not isinstance(candidates, (list, tuple)):
        raise TypeError("candidates must be a list or tuple to preserve deterministic order")
    normalized: list[RerankCandidate] = []
    seen: set[str] = set()
    for item in candidates:
        if not isinstance(item, RerankCandidate):
            raise TypeError("candidates must contain RerankCandidate objects")
        validate_id(item.id, "candidate")
        if item.id in seen:
            raise ValueError(f"duplicate candidate ID: {item.id}")
        if not isinstance(item.text, str) or not item.text.strip():
            raise ValueError(f"candidate {item.id!r} text must be nonempty")
        normalized.append(item)
        seen.add(item.id)
    return tuple(normalized)
