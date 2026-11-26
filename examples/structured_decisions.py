"""Run a pure-text bundle whose named questions preserve JSON structure."""

from __future__ import annotations

import argparse
from pathlib import Path

from pyjev import Jev

CONFIG = Path(__file__).with_name(".pyjev.toml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", default="Refund requested after checkout error")
    parser.add_argument("--body", default="The checkout failed twice and I was charged once.")
    parser.add_argument("--sender-name", default="Northstar Supplies")
    parser.add_argument("--sender-email", default="buyer@example.invalid")
    parser.add_argument("--requested-action", default="Please refund the duplicate charge.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = {
        "subject": args.subject,
        "body": args.body,
        "sender": {"display_name": args.sender_name, "email": args.sender_email},
        "requested_action": args.requested_action,
    }

    with Jev() as jev:
        result = jev.decide("structured-ticket", state=state, config=CONFIG)

    route = result.answers["route"]
    sender_conflict = result.answers["sender-conflict"]
    urgency = result.answers["urgency"]
    print("route:", route.value)
    print("route probabilities:", route.probabilities)
    print("route confidence:", route.confidence)
    print("sender-conflict probability:", sender_conflict.value)
    print("urgency score:", urgency.value)
    print("urgency confidence:", urgency.confidence)
    print("model:", result.model)
    print("request_id:", result.request_id)
    print("Select thresholds and application actions in ordinary Python policy.")


if __name__ == "__main__":
    main()
