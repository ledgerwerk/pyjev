from __future__ import annotations

import inspect
import math

import pytest

import pyjev.pipeline as pipeline
from pyjev import BundleResult, ChoiceResult, NoulResult, ScoreResult
from pyjev.pipeline import (
    Accepted,
    PipelineLookupError,
    PipelineTypeError,
    Rejected,
    answer,
    require_confidence,
    require_probability,
)


def choice(value: str = "billing", confidence: float = 0.85) -> ChoiceResult:
    return ChoiceResult(
        value=value,
        confidence=confidence,
        probabilities={value: confidence, "other": 1 - confidence},
        model="test-model",
        usage={},
        raw={"choice": value, "confidence": confidence},
    )


def score(value: float = 2.5, confidence: float = 0.85) -> ScoreResult:
    return ScoreResult(
        value=value,
        confidence=confidence,
        probabilities={2: 0.2, 3: 0.8},
        legend={2: "normal", 3: "urgent"},
        model="test-model",
        usage={},
        raw={"score": value, "confidence": confidence},
    )


def noul(value: float = 0.85) -> NoulResult:
    return NoulResult(value=value, model="test-model", usage={}, raw={"noul": value})


def bundle(**answers: object) -> BundleResult:
    return BundleResult(answers=answers, model="test-model", usage={}, raw={})


@pytest.mark.parametrize("threshold", [-0.01, 1.01, math.nan, math.inf, -math.inf])
def test_require_confidence_rejects_invalid_threshold(threshold: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        require_confidence(threshold)


def test_require_probability_requires_exactly_one_bound() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        require_probability()
    with pytest.raises(ValueError, match="exactly one"):
        require_probability(at_least=0.5, at_most=0.5)


def test_require_probability_rejects_invalid_thresholds() -> None:
    for kwargs in ({"at_least": -0.1}, {"at_most": 1.1}, {"at_least": math.nan}):
        with pytest.raises(ValueError, match="between 0 and 1"):
            require_probability(**kwargs)


def test_answer_requires_nonempty_name() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        answer("")


def test_answer_selects_existing_bundle_child_by_identity() -> None:
    child = choice()
    result = bundle(intent=child)

    assert result | answer("intent") is child


def test_answer_rejects_primitive_result() -> None:
    with pytest.raises(PipelineTypeError, match="BundleResult"):
        choice() | answer("intent")


def test_answer_unknown_key_mentions_available_answers() -> None:
    with pytest.raises(PipelineLookupError, match="missing.*intent.*urgency"):
        bundle(intent=choice(), urgency=score()) | answer("missing")


def test_confidence_gate_accepts_choice_above_threshold() -> None:
    result = choice(confidence=0.85)

    outcome = result | require_confidence(0.80)

    assert isinstance(outcome, Accepted)
    assert outcome.value == "billing"
    assert outcome.result is result
    assert outcome.gate.observed == 0.85
    assert outcome.gate.comparator == "at_least"


def test_confidence_gate_accepts_choice_exactly_at_threshold() -> None:
    result = choice(confidence=0.70)

    assert (result | require_confidence(0.70)).passed is True


def test_confidence_gate_rejects_choice_below_threshold() -> None:
    result = choice(confidence=0.69)

    outcome = result | require_confidence(0.70)

    assert isinstance(outcome, Rejected)
    assert outcome.passed is False
    assert outcome.result is result
    assert not hasattr(outcome, "value")


def test_confidence_gate_accepts_score() -> None:
    result = score(confidence=0.90)

    outcome = result | require_confidence(0.90)

    assert isinstance(outcome, Accepted)
    assert outcome.value == 2.5
    assert outcome.result is result


@pytest.mark.parametrize("result", [noul(), bundle(intent=choice())])
def test_confidence_gate_rejects_incompatible_result_types(result: object) -> None:
    with pytest.raises(PipelineTypeError, match="ChoiceResult or ScoreResult"):
        result | require_confidence(0.70)


def test_rejected_confidence_preserves_complete_result() -> None:
    result = choice(confidence=0.20)

    outcome = result | require_confidence(0.80)

    assert isinstance(outcome, Rejected)
    assert outcome.result.to_dict() == result.to_dict()
    assert outcome.gate.observed == 0.20


def test_probability_at_least_accepts_noul() -> None:
    result = noul(0.80)

    outcome = result | require_probability(at_least=0.80)

    assert isinstance(outcome, Accepted)
    assert outcome.value == 0.80
    assert outcome.result is result


def test_probability_at_least_rejects_noul() -> None:
    result = noul(0.79)

    outcome = result | require_probability(at_least=0.80)

    assert isinstance(outcome, Rejected)
    assert outcome.result is result
    assert not hasattr(outcome, "value")


def test_probability_at_most_accepts_noul() -> None:
    result = noul(0.20)

    outcome = result | require_probability(at_most=0.20)

    assert isinstance(outcome, Accepted)
    assert outcome.value == 0.20
    assert outcome.gate.comparator == "at_most"


def test_probability_at_most_rejects_noul() -> None:
    result = noul(0.21)

    assert isinstance(result | require_probability(at_most=0.20), Rejected)


def test_probability_gate_rejects_choice_type() -> None:
    with pytest.raises(PipelineTypeError, match="NoulResult"):
        choice() | require_probability(at_least=0.70)


def test_stage_chain_runs_left_to_right() -> None:
    result = bundle(intent=choice(confidence=0.70))

    outcome = result | answer("intent") | require_confidence(0.70)

    assert isinstance(outcome, Accepted)
    assert outcome.value == "billing"


def test_reusable_bundle_policy() -> None:
    policy = answer("intent") | require_confidence(0.70)

    accepted = bundle(intent=choice(confidence=0.70)) | policy
    rejected = bundle(intent=choice(confidence=0.69)) | policy

    assert isinstance(accepted, Accepted)
    assert isinstance(rejected, Rejected)


def test_result_pipe_does_not_modify_original_result() -> None:
    result = bundle(intent=choice(confidence=0.70))
    original_answers = result.answers.copy()

    result | answer("intent") | require_confidence(0.80)

    assert result.answers == original_answers


def test_pipeline_module_never_constructs_client() -> None:
    source = inspect.getsource(pipeline)

    assert "TypeSafeClient" not in source
    assert "Jev(" not in source
