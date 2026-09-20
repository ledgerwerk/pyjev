"""Demonstrate a direct Choice decision and how application code uses uncertainty."""

from __future__ import annotations

import json

from pyjev import Jev

QUESTION = "Which snack should the on-call engineer bring?"
STATE = {
    "incident": "The checkout service is degraded during a Friday-night deploy.",
    "on_call": {
        "condition": "skipped dinner",
        "hands": "typing continuously",
        "mood": "one failed retry away from naming servers after enemies",
    },
    "constraints": [
        "must be edible one-handed",
        "must not make the keyboard sticky",
        "must survive sitting beside a warm laptop",
    ],
}
CHOICES = {
    "banana": "Fast fuel, portable, peel keeps the keyboard clean",
    "pretzels": "Salty, dry, durable, and compatible with incident keyboards",
    "chocolate": "Excellent morale boost, but risky near warm hardware",
    "ramen": "Emotionally correct, operationally incompatible with one-handed typing",
}
AUTO_ACCEPT_CONFIDENCE = 0.75


def main() -> None:
    print("=== Emergency Snack Tribunal ===")
    print("This is a direct Jev Choice: structured state + one closed set of options.\n")

    print("State sent to Jev:")
    print(json.dumps(STATE, indent=2))

    print("\nQuestion:")
    print(f"  {QUESTION}")

    print("\nAllowed choices:")
    for label, description in CHOICES.items():
        print(f"  {label:9} {description}")

    with Jev() as jev:
        result = jev.choice(
            QUESTION,
            state=STATE,
            choices=CHOICES,
        )

    print("\nStructured result:")
    print(f"  selected    {result.value}")
    print(f"  confidence  {result.confidence:.2f}")
    print(f"  model       {result.model}")
    if result.request_id:
        print(f"  request_id  {result.request_id}")

    print("\nProbability distribution:")
    for label, probability in sorted(
        result.probabilities.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        selected = "  <-- selected" if label == result.value else ""
        print(f"  {label:9} {probability:6.1%}{selected}")

    print("\nApplication policy:")
    print("  Confidence is a separate signal from the selected option's probability.")
    print(
        f"  The demo auto-accept threshold is {AUTO_ACCEPT_CONFIDENCE:.2f}; it is application policy, not a Jev rule.",
    )
    if result.confidence >= AUTO_ACCEPT_CONFIDENCE:
        print(
            f"  confidence >= {AUTO_ACCEPT_CONFIDENCE:.2f}: trust the structured decision "
            f"and send {result.value!r} to the snack-fetching robot."
        )
    else:
        print(
            f"  confidence < {AUTO_ACCEPT_CONFIDENCE:.2f}: do not automate lunch. "
            "The on-call human keeps snack sovereignty."
        )


if __name__ == "__main__":
    main()
