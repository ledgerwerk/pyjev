"""Demonstrate a reusable named Score decision and confidence-aware application logic."""

from __future__ import annotations

import json
from pathlib import Path

from pyjev import Jev

CONFIG = Path(__file__).with_name(".pyjev.toml")
DECISION = "haunted-ci"
STATE = {
    "workflow": "release",
    "clock": "02:13",
    "symptom": ("Integration tests pass twice, then fail on the third retry with no code changes."),
    "release_blocked": True,
    "recent_changes": ["dependency refresh", "new cache key"],
    "evidence": [
        "rerunning the failed shard sometimes fixes it",
        "the failure moved to a different test after clearing the cache",
        "nobody can reproduce it locally",
    ],
    "humans_awake": False,
}
ACT_CONFIDENCE = 0.65


def main() -> None:
    print("=== Haunted CI Triage ===")
    print(
        "This is a named pyjev Score decision: the question and ordered rubric "
        f"live in {CONFIG.name}, while runtime state stays in Python.\n"
    )

    print(f"Decision name: {DECISION}")
    print("State sent to Jev:")
    print(json.dumps(STATE, indent=2))

    with Jev() as jev:
        result = jev.decide(
            DECISION,
            state=STATE,
            config=CONFIG,
        )

    print("\nStructured result:")
    print(f"  score       {result.value:.2f}")
    print(f"  confidence  {result.confidence:.2f}")
    print(f"  model       {result.model}")
    if result.request_id:
        print(f"  request_id  {result.request_id}")

    print("\nScore rubric and probability distribution:")
    for level in sorted(result.legend):
        description = result.legend[level]
        probability = result.probabilities[level]
        print(f"  {level}: {probability:6.1%}  {description}")

    print(
        "\nThe score may be fractional: it is the probability-weighted position "
        "across the ordered levels, not a hidden fifth label."
    )

    print("\nApplication policy:")
    print(f"  The demo action threshold is {ACT_CONFIDENCE:.2f}; it is application policy, not a Jev rule.")
    if result.confidence < ACT_CONFIDENCE:
        print(
            f"  confidence < {ACT_CONFIDENCE:.2f}: do not wake anybody based on "
            "ghost vibes. Collect more evidence or ask a human to review."
        )
    else:
        nearest_level = min(
            result.legend,
            key=lambda level: abs(level - result.value),
        )
        print(
            f"  confidence >= {ACT_CONFIDENCE:.2f}: nearest rubric level is "
            f"{nearest_level}; application action = "
            f"{result.legend[nearest_level]!r}"
        )


if __name__ == "__main__":
    main()
