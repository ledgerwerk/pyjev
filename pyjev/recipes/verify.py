"""Verify claims against supplied evidence without web retrieval or side effects."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ..client import AsyncJev, Jev
from ..decisions import BundleDecision, ChoiceDecision, decision_to_dict
from ..results import BundleResult, ChoiceResult

_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
_NO_SOURCE = "__none__"
MAX_EVIDENCE_SOURCES = 254
MAX_CLAIMS = 64
_RELATION_OPTIONS = {
    "supports": "The supplied evidence supports the claim.",
    "contradicts": "The supplied evidence contradicts the claim.",
    "says_nothing": "The supplied evidence does not address the claim.",
}
_VERDICTS: dict[str, Literal["verified", "contradicted", "unsupported"]] = {
    "supports": "verified",
    "contradicts": "contradicted",
    "says_nothing": "unsupported",
}


@dataclass(frozen=True, slots=True)
class Claim:
    """A claim with a stable identifier for bundle keys and result correlation."""

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class Evidence:
    """A caller-supplied evidence source; the recipe never fetches it."""

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class ClaimPlan:
    claim: Claim
    relation_key: str
    source_key: str | None


@dataclass(frozen=True, slots=True)
class VerifyPlan:
    """Inspect-before-execute plan for a bundled verification request."""

    claims: tuple[ClaimPlan, ...]
    evidence: tuple[Evidence, ...]
    state: dict[str, Any]
    decision: BundleDecision
    auto_accept: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "decision": decision_to_dict(self.decision),
            "claims": [
                {
                    "id": item.claim.id,
                    "text": item.claim.text,
                    "relation_key": item.relation_key,
                    "source_key": item.source_key,
                }
                for item in self.claims
            ],
            "evidence": [{"id": item.id, "text": item.text} for item in self.evidence],
            "policy": {"auto_accept": self.auto_accept},
        }


@dataclass(frozen=True, slots=True)
class ClaimVerdict:
    """One claim's semantic verdict, optional source judgment, and retained evidence."""

    claim_id: str
    claim: str
    verdict: Literal["verified", "contradicted", "unsupported"]
    confidence: float
    probabilities: dict[str, float]
    source_id: str | None
    evidence_source: Evidence | None
    supporting_evidence: Evidence | None
    action: Literal["auto_accept", "review"]
    relation_result: ChoiceResult
    source_result: ChoiceResult | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim": self.claim,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "probabilities": dict(self.probabilities),
            "source_id": self.source_id,
            "evidence_source": _evidence_dict(self.evidence_source),
            "supporting_evidence": _evidence_dict(self.supporting_evidence),
            "action": self.action,
            "relation_result": self.relation_result.to_dict(),
            "source_result": self.source_result.to_dict() if self.source_result is not None else None,
        }


@dataclass(frozen=True, slots=True)
class VerifySummary:
    total: int
    verified: int
    contradicted: int
    unsupported: int
    auto_accepted: int
    review: int

    def to_dict(self) -> dict[str, int]:
        return {
            "total": self.total,
            "verified": self.verified,
            "contradicted": self.contradicted,
            "unsupported": self.unsupported,
            "auto_accepted": self.auto_accepted,
            "review": self.review,
        }


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """Claim verdicts, exact summary counts, and the complete underlying bundle."""

    results: tuple[ClaimVerdict, ...]
    summary: VerifySummary
    decision: BundleResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [result.to_dict() for result in self.results],
            "summary": self.summary.to_dict(),
            "decision": self.decision.to_dict(),
        }


def build_verify(
    claims: Sequence[Claim | str | tuple[str, str]],
    evidence: Sequence[Evidence | str | tuple[str, str]],
    *,
    auto_accept: float | None = None,
    model: str | None = None,
    max_claims: int = MAX_CLAIMS,
) -> VerifyPlan:
    """Normalize IDs and build independent claim judgments in one bundle.

    Plain strings receive deterministic positional IDs. Use ``Claim`` or ``(id, text)``
    pairs when caller-owned identifiers must round-trip. Multiple evidence sources add
    one source-selection Choice per claim, including an explicit no-source option.
    """
    normalized_claims = _normalize_claims(claims)
    normalized_evidence = _normalize_evidence(evidence)
    if not normalized_claims:
        raise ValueError("verify requires at least one claim")
    if not normalized_evidence:
        raise ValueError("verify requires at least one evidence source")
    if isinstance(max_claims, bool) or not isinstance(max_claims, int) or not 1 <= max_claims <= MAX_CLAIMS:
        raise ValueError(f"max_claims must be between 1 and {MAX_CLAIMS}")
    if len(normalized_claims) > max_claims:
        raise ValueError(f"verify received {len(normalized_claims)} claims, over max_claims={max_claims}")
    if len(normalized_evidence) > MAX_EVIDENCE_SOURCES:
        raise ValueError(f"verify supports at most {MAX_EVIDENCE_SOURCES} evidence sources")
    if auto_accept is not None:
        auto_accept = _threshold(auto_accept)
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError("model must be a nonempty string or None")

    state = {
        "claims": [{"id": claim.id, "text": claim.text} for claim in normalized_claims],
        "evidence": [{"id": source.id, "text": source.text} for source in normalized_evidence],
    }
    questions: dict[str, ChoiceDecision] = {}
    claim_plans: list[ClaimPlan] = []
    for index, claim in enumerate(normalized_claims):
        relation_key = f"relation_{index:04d}"
        questions[relation_key] = ChoiceDecision(
            name=relation_key,
            question=(
                f"Assess claim {claim.id!r} only against the supplied evidence. "
                "Choose supports, contradicts, or says_nothing. Use says_nothing when the evidence does not address it."
            ),
            options=dict(_RELATION_OPTIONS),
        )
        source_key: str | None = None
        if len(normalized_evidence) > 1:
            source_key = f"source_{index:04d}"
            source_options: dict[str, str | None] = {source.id: source.text for source in normalized_evidence}
            source_options[_NO_SOURCE] = "No single supplied source is the basis for the judgment."
            questions[source_key] = ChoiceDecision(
                name=source_key,
                question=f"Which supplied evidence source, if any, is most relevant to claim {claim.id!r}?",
                options=source_options,
            )
        claim_plans.append(ClaimPlan(claim, relation_key, source_key))

    return VerifyPlan(
        claims=tuple(claim_plans),
        evidence=normalized_evidence,
        state=state,
        decision=BundleDecision(name="verify", questions=questions, model=model),
        auto_accept=auto_accept,
    )


def interpret_verify(plan: VerifyPlan, decision: BundleResult) -> VerifyResult:
    """Map typed relation choices to distinct deterministic semantic verdicts."""
    if not isinstance(decision, BundleResult):
        raise TypeError("verification interpretation requires a BundleResult")
    evidence_by_id = {source.id: source for source in plan.evidence}
    results: list[ClaimVerdict] = []
    for item in plan.claims:
        relation = decision.answers.get(item.relation_key)
        if not isinstance(relation, ChoiceResult):
            raise ValueError(f"verification result is missing relation for claim {item.claim.id!r}")
        if relation.value not in _VERDICTS:
            raise ValueError(f"verification returned an unknown relation for claim {item.claim.id!r}")
        _validate_confidence(relation.confidence, f"relation for claim {item.claim.id!r}")
        verdict = _VERDICTS[relation.value]
        source_result: ChoiceResult | None = None
        source_id: str | None = None
        evidence_source: Evidence | None = None
        source_confident = True
        if item.source_key is not None:
            source_answer = decision.answers.get(item.source_key)
            if not isinstance(source_answer, ChoiceResult):
                raise ValueError(f"verification result is missing evidence source for claim {item.claim.id!r}")
            _validate_confidence(source_answer.confidence, f"source for claim {item.claim.id!r}")
            source_result = source_answer
            if source_answer.value != _NO_SOURCE:
                if source_answer.value not in evidence_by_id:
                    raise ValueError(f"verification selected unknown evidence ID {source_answer.value!r}")
                source_id = source_answer.value
                evidence_source = evidence_by_id[source_id]
            source_confident = (
                plan.auto_accept is not None
                and source_answer.value != _NO_SOURCE
                and source_answer.confidence >= plan.auto_accept
            )
        else:
            evidence_source = plan.evidence[0]
            source_id = evidence_source.id

        auto = (
            plan.auto_accept is not None
            and verdict == "verified"
            and relation.confidence >= plan.auto_accept
            and source_confident
        )
        results.append(
            ClaimVerdict(
                claim_id=item.claim.id,
                claim=item.claim.text,
                verdict=verdict,
                confidence=relation.confidence,
                probabilities=dict(relation.probabilities),
                source_id=source_id,
                evidence_source=evidence_source,
                supporting_evidence=evidence_source if verdict == "verified" else None,
                action="auto_accept" if auto else "review",
                relation_result=relation,
                source_result=source_result,
            )
        )

    summary = VerifySummary(
        total=len(results),
        verified=sum(result.verdict == "verified" for result in results),
        contradicted=sum(result.verdict == "contradicted" for result in results),
        unsupported=sum(result.verdict == "unsupported" for result in results),
        auto_accepted=sum(result.action == "auto_accept" for result in results),
        review=sum(result.action == "review" for result in results),
    )
    return VerifyResult(tuple(results), summary, decision)


def execute_verify(jev: Jev, plan: VerifyPlan) -> VerifyResult:
    """Execute a prepared verify plan through the supplied sync client."""
    result = jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, BundleResult):
        raise TypeError("Jev.evaluate returned a non-bundle result for a verify plan")
    return interpret_verify(plan, result)


async def aexecute_verify(jev: AsyncJev, plan: VerifyPlan) -> VerifyResult:
    """Native async counterpart to :func:`execute_verify`."""
    result = await jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, BundleResult):
        raise TypeError("AsyncJev.evaluate returned a non-bundle result for a verify plan")
    return interpret_verify(plan, result)


def verify(
    jev: Jev,
    claims: Sequence[Claim | str | tuple[str, str]],
    evidence: Sequence[Evidence | str | tuple[str, str]],
    *,
    auto_accept: float | None = None,
    model: str | None = None,
    max_claims: int = MAX_CLAIMS,
) -> VerifyResult:
    """Build and execute independent claim judgments against supplied evidence."""
    plan = build_verify(claims, evidence, auto_accept=auto_accept, model=model, max_claims=max_claims)
    return execute_verify(jev, plan)


async def averify(
    jev: AsyncJev,
    claims: Sequence[Claim | str | tuple[str, str]],
    evidence: Sequence[Evidence | str | tuple[str, str]],
    *,
    auto_accept: float | None = None,
    model: str | None = None,
    max_claims: int = MAX_CLAIMS,
) -> VerifyResult:
    """Async build and execution counterpart to :func:`verify`."""
    plan = build_verify(claims, evidence, auto_accept=auto_accept, model=model, max_claims=max_claims)
    return await aexecute_verify(jev, plan)


def _normalize_claims(claims: Sequence[Claim | str | tuple[str, str]]) -> tuple[Claim, ...]:
    if not isinstance(claims, (list, tuple)):
        raise TypeError("claims must be a list or tuple")
    result: list[Claim] = []
    for index, item in enumerate(claims):
        if isinstance(item, Claim):
            claim = item
        elif isinstance(item, str):
            claim = Claim(f"claim-{index:04d}", item)
        elif isinstance(item, tuple) and len(item) == 2:
            claim = Claim(item[0], item[1])
        else:
            raise TypeError("claims must contain Claim, text, or (id, text) values")
        _validate_record(claim.id, claim.text, "claim")
        result.append(claim)
    _unique_ids((claim.id for claim in result), "claim")
    return tuple(result)


def _normalize_evidence(evidence: Sequence[Evidence | str | tuple[str, str]]) -> tuple[Evidence, ...]:
    if not isinstance(evidence, (list, tuple)):
        raise TypeError("evidence must be a list or tuple")
    result: list[Evidence] = []
    for index, item in enumerate(evidence):
        if isinstance(item, Evidence):
            source = item
        elif isinstance(item, str):
            source = Evidence(f"evidence-{index:04d}", item)
        elif isinstance(item, tuple) and len(item) == 2:
            source = Evidence(item[0], item[1])
        else:
            raise TypeError("evidence must contain Evidence, text, or (id, text) values")
        _validate_record(source.id, source.text, "evidence")
        result.append(source)
    _unique_ids((source.id for source in result), "evidence")
    return tuple(result)


def _validate_record(identifier: str, text: str, kind: str) -> None:
    if isinstance(identifier, str) and identifier == _NO_SOURCE:
        raise ValueError(f"{kind} ID {identifier!r} is reserved")
    if not isinstance(identifier, str) or _ID_PATTERN.fullmatch(identifier) is None:
        raise ValueError(f"{kind} IDs must match [A-Za-z0-9][A-Za-z0-9_.:-]{0, 63}")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{kind} text must be nonempty")


def _unique_ids(ids: Any, kind: str) -> None:
    seen: set[str] = set()
    for identifier in ids:
        if identifier in seen:
            raise ValueError(f"duplicate {kind} ID: {identifier}")
        seen.add(identifier)


def _threshold(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("auto_accept must be a finite number between 0 and 1")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 <= normalized <= 1:
        raise ValueError("auto_accept must be a finite number between 0 and 1")
    return normalized


def _validate_confidence(value: float, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError(f"invalid confidence {label}")


def _evidence_dict(source: Evidence | None) -> dict[str, str] | None:
    return {"id": source.id, "text": source.text} if source is not None else None
