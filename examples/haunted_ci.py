"""Use a reusable named Score decision with structured state."""

from pathlib import Path

from pyjev import Jev

CONFIG = Path(__file__).with_name(".pyjev.toml")


def main() -> None:
    state = {
        "workflow": "release",
        "symptom": "The integration job fails only on the third retry.",
        "recent_changes": ["dependency refresh", "new cache key"],
        "humans_awake": True,
    }
    with Jev() as jev:
        result = jev.decide("haunted-ci", state=state, config=CONFIG)
    print(f"score={result.value} confidence={result.confidence:.2f}")


if __name__ == "__main__":
    main()
