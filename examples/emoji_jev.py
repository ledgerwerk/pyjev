"""Interactive Emoji Jev example using one named bundle per message."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from pyjev import BundleResult, ChoiceResult, Jev, NoulResult, ScoreResult

CONFIG = Path(__file__).with_name(".pyjev.toml")
DECISION = "emoji-jev"
TOP_PICKS = 5

EMOJI = {
    "grinning": "😀",
    "joy_tears": "😂",
    "rofl": "🤣",
    "smiling_eyes": "😊",
    "heart_eyes": "😍",
    "star_struck": "🤩",
    "kiss": "😘",
    "yum": "😋",
    "tongue_wink": "😜",
    "hugging": "🤗",
    "thinking": "🤔",
    "raised_eyebrow": "🤨",
    "neutral": "😐",
    "smirk": "😏",
    "unamused": "😒",
    "eye_roll": "🙄",
    "grimace": "😬",
    "relieved": "😌",
    "pensive": "😔",
    "sleeping": "😴",
    "mask": "😷",
    "exploding_head": "🤯",
    "partying": "🥳",
    "sunglasses": "😎",
    "nerd": "🤓",
    "confused": "😕",
    "worried": "😟",
    "flushed": "😳",
    "pleading": "🥺",
    "fearful": "😨",
    "anxious_sweat": "😰",
    "crying": "😢",
    "loudly_crying": "😭",
    "screaming": "😱",
    "disappointed": "😞",
    "weary": "😩",
    "tired_face": "😫",
    "yawning": "🥱",
    "angry": "😠",
    "rage": "😡",
    "cursing": "🤬",
    "smiling_imp": "😈",
    "skull": "💀",
    "clown": "🤡",
    "sweat_smile": "😅",
    "upside_down": "🙃",
    "smiling_tear": "🥲",
    "melting": "🫠",
    "holding_back_tears": "🥹",
    "heart": "❤️",
    "broken_heart": "💔",
    "fire": "🔥",
    "sparkles": "✨",
    "hundred": "💯",
    "eyes": "👀",
    "thumbs_up": "👍",
    "clap": "👏",
    "raised_hands": "🙌",
    "pray": "🙏",
    "facepalm": "🤦",
    "shrug": "🤷",
    "muscle": "💪",
    "party_popper": "🎉",
    "rocket": "🚀",
}


@dataclass(frozen=True, slots=True)
class EmojiReport:
    result: BundleResult
    elapsed_ms: float


def _answers(
    result: BundleResult,
) -> tuple[
    ChoiceResult,
    ChoiceResult,
    ScoreResult,
    ScoreResult,
    ScoreResult,
    NoulResult,
    NoulResult,
    NoulResult,
]:
    emoji = result.answers["emoji"]
    emotion = result.answers["emotion"]
    mood = result.answers["mood"]
    urgency = result.answers["urgency"]
    energy = result.answers["energy"]
    wants_reply = result.answers["wants-reply"]
    sarcasm = result.answers["sarcasm"]
    joke = result.answers["joke"]
    values = (
        ("emoji", emoji, ChoiceResult),
        ("emotion", emotion, ChoiceResult),
        ("mood", mood, ScoreResult),
        ("urgency", urgency, ScoreResult),
        ("energy", energy, ScoreResult),
        ("wants-reply", wants_reply, NoulResult),
        ("sarcasm", sarcasm, NoulResult),
        ("joke", joke, NoulResult),
    )
    for name, value, expected_type in values:
        if not isinstance(value, expected_type):
            raise TypeError(f"{name} must be {expected_type.__name__}, got {type(value).__name__}")
    return emoji, emotion, mood, urgency, energy, wants_reply, sarcasm, joke


def analyze_text(jev: Jev, text: str) -> EmojiReport:
    """Analyze one message with one named bundle request."""
    started = perf_counter()
    result = jev.decide(DECISION, state={"text": text}, config=CONFIG)
    elapsed_ms = (perf_counter() - started) * 1000.0
    if not isinstance(result, BundleResult):
        raise TypeError(f"Expected BundleResult, got {type(result).__name__}")
    return EmojiReport(result=result, elapsed_ms=elapsed_ms)


def top_emoji_picks(
    result: ChoiceResult,
    *,
    limit: int = TOP_PICKS,
) -> list[tuple[str, str, float]]:
    """Return the highest-probability emoji choices in deterministic order."""
    ranked = sorted(result.probabilities.items(), key=lambda item: item[1], reverse=True)
    return [(key, EMOJI.get(key, "�"), probability) for key, probability in ranked[:limit]]


def nearest_score_label(result: ScoreResult) -> str:
    """Return the nearest ordered legend label for display."""
    level = min(result.legend, key=lambda item: abs(item - result.value))
    return str(result.legend[level])


def usage_value(usage: dict[str, Any], *names: str) -> Any | None:
    """Read the first available usage key."""
    for name in names:
        if name in usage:
            return usage[name]
    return None


def _print_score(name: str, result: ScoreResult) -> None:
    maximum = max(result.legend)
    print(
        f"  {name:<10} {result.value:>4.2f} / {maximum}  ~ "
        f"{nearest_score_label(result):<12} confidence={result.confidence:.2f}",
    )


def print_report(report: EmojiReport) -> None:
    """Print the structured result and client-observed request metadata."""
    emoji, emotion, mood, urgency, energy, wants_reply, sarcasm, joke = _answers(report.result)
    primary = EMOJI.get(emoji.value, "�")
    print(f"\n{primary}  {emoji.value}")
    print("\ntop emoji picks")
    for key, char, probability in top_emoji_picks(emoji):
        selected = "  <-- selected" if key == emoji.value else ""
        print(f"  {char} {key:<20} {probability * 100:>5.1f}%{selected}")

    print("\ntone")
    print(f"  {'emotion':<10} {emotion.value:<16} confidence={emotion.confidence:.2f}")
    _print_score("mood", mood)
    _print_score("urgency", urgency)
    _print_score("energy", energy)
    print(f"  {'reply':<10} {wants_reply.value:.2f}")
    print(f"  {'sarcasm':<10} {sarcasm.value:.2f}")
    print(f"  {'joke':<10} {joke.value:.2f}")

    usage = report.result.usage
    print("\nrequest")
    print(f"  {'emoji confidence':<18} {emoji.confidence:.2f}")
    print(f"  {'round trip':<18} {report.elapsed_ms:.0f} ms")
    print(f"  {'model':<18} {report.result.model}")
    if report.result.request_id:
        print(f"  {'request_id':<18} {report.result.request_id}")
    for label, names in (
        ("input tokens", ("input_tokens", "inputTokens")),
        ("output tokens", ("output_tokens", "outputTokens")),
        ("total tokens", ("total_tokens", "totalTokens")),
    ):
        value = usage_value(usage, *names)
        if value is not None:
            print(f"  {label:<18} {value}")


def main() -> None:
    print("=== Emoji Jev ===")
    print("Type a message and Jev will classify it into emoji + tone signals.")
    print("One input = one Jev bundle request.")
    print("Commands: q / quit / exit\n")

    with Jev() as jev:
        while True:
            try:
                text = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye")
                return

            if text.lower() in {"q", "quit", "exit"}:
                print("bye")
                return
            if not text:
                continue

            try:
                print_report(analyze_text(jev, text))
            except Exception as exc:
                print(f"error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
