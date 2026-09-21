from __future__ import annotations

from pathlib import Path

from examples.emoji_jev import (
    CONFIG,
    EMOJI,
    EmojiReport,
    analyze_text,
    nearest_score_label,
    print_report,
    top_emoji_picks,
)
from pyjev import BundleResult, ChoiceResult, NoulResult, ScoreResult
from pyjev.decisions import BundleDecision, ChoiceDecision, NoulDecision, ScoreDecision, load_decision

EXPECTED_QUESTIONS = {
    "emoji",
    "emotion",
    "mood",
    "urgency",
    "energy",
    "wants-reply",
    "sarcasm",
    "joke",
}


def make_bundle() -> BundleResult:
    return BundleResult(
        answers={
            "emoji": ChoiceResult(
                value="rocket",
                confidence=0.81,
                probabilities={"rocket": 0.51, "fire": 0.31, "party_popper": 0.18},
                model="test",
                usage={"input_tokens": 10},
                raw={},
            ),
            "emotion": ChoiceResult(
                value="joy",
                confidence=0.79,
                probabilities={"joy": 0.79, "neutral": 0.21},
                model="test",
                usage={},
                raw={},
            ),
            "mood": ScoreResult(
                value=3.42,
                confidence=0.63,
                probabilities={0: 0.01, 1: 0.04, 2: 0.2, 3: 0.5, 4: 0.25},
                legend={0: "devastated", 1: "down", 2: "neutral", 3: "upbeat", 4: "ecstatic"},
                model="test",
                usage={},
                raw={},
            ),
            "urgency": ScoreResult(
                value=1.71,
                confidence=0.82,
                probabilities={0: 0.1, 1: 0.2, 2: 0.7},
                legend={0: "no rush", 1: "soon", 2: "right now"},
                model="test",
                usage={},
                raw={},
            ),
            "energy": ScoreResult(
                value=1.83,
                confidence=0.88,
                probabilities={0: 0.1, 1: 0.2, 2: 0.7},
                legend={0: "flat", 1: "steady", 2: "buzzing"},
                model="test",
                usage={},
                raw={},
            ),
            "wants-reply": NoulResult(value=0.26, model="test", usage={}, raw={}),
            "sarcasm": NoulResult(value=0.07, model="test", usage={}, raw={}),
            "joke": NoulResult(value=0.22, model="test", usage={}, raw={}),
        },
        model="test",
        usage={"input_tokens": 812, "output_tokens": 7, "total_tokens": 819},
        raw={},
        request_id="req-test",
    )


def test_configuration_contract() -> None:
    decision = load_decision("emoji-jev", CONFIG)
    assert isinstance(decision, BundleDecision)
    assert set(decision.questions) == EXPECTED_QUESTIONS

    emoji = decision.questions["emoji"]
    assert isinstance(emoji, ChoiceDecision)
    assert len(emoji.options) == 64
    assert set(emoji.options) == set(EMOJI)

    assert isinstance(decision.questions["emotion"], ChoiceDecision)
    assert isinstance(decision.questions["mood"], ScoreDecision)
    assert isinstance(decision.questions["urgency"], ScoreDecision)
    assert isinstance(decision.questions["energy"], ScoreDecision)
    assert isinstance(decision.questions["wants-reply"], NoulDecision)
    assert isinstance(decision.questions["sarcasm"], NoulDecision)
    assert isinstance(decision.questions["joke"], NoulDecision)
    assert len(decision.questions["mood"].levels) == 5
    assert len(decision.questions["urgency"].levels) == 3
    assert len(decision.questions["energy"].levels) == 3


def test_top_emoji_picks_are_sorted_and_mapped() -> None:
    result = make_bundle().answers["emoji"]
    assert isinstance(result, ChoiceResult)
    assert top_emoji_picks(result) == [
        ("rocket", "🚀", 0.51),
        ("fire", "🔥", 0.31),
        ("party_popper", "🎉", 0.18),
    ]


def test_nearest_score_label_preserves_fractional_value() -> None:
    result = make_bundle().answers["mood"]
    assert isinstance(result, ScoreResult)
    original = result.value
    assert nearest_score_label(result) == "upbeat"
    assert result.value == original == 3.42


def test_analyze_text_makes_one_bundle_request() -> None:
    class FakeJev:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str], Path | None]] = []

        def decide(self, name: str, *, state: dict[str, str], config: Path | None = None) -> BundleResult:
            self.calls.append((name, state, config))
            return make_bundle()

    jev = FakeJev()
    report = analyze_text(jev, "shipped it")  # type: ignore[arg-type]

    assert isinstance(report, EmojiReport)
    assert len(jev.calls) == 1
    assert jev.calls[0] == ("emoji-jev", {"text": "shipped it"}, CONFIG)


def test_print_report_has_human_readable_sections(capsys) -> None:
    print_report(EmojiReport(result=make_bundle(), elapsed_ms=93.0))
    output = capsys.readouterr().out
    for phrase in ("top emoji picks", "tone", "request", "emoji confidence", "round trip", "model"):
        assert phrase in output
