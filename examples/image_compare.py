"""Compare a candidate image with a caller-supplied named reference image."""

from __future__ import annotations

import argparse
from pathlib import Path

from pyjev import Image, Jev


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="path to a candidate PNG or JPEG image")
    parser.add_argument("reference", type=Path, help="path to a reference PNG or JPEG image")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidate = Image(args.candidate)
    reference = Image(args.reference)

    with Jev(images=True) as jev:
        result = jev.noul(
            "Does the object in `candidate` visually match <reference>?",
            state={"candidate": candidate},
            true="The visible object is consistent with the reference image.",
            false="The visible object differs materially from the reference image.",
            assets={"<reference>": reference},
        )

    print("probability true:", result.value)
    print("request_id:", result.request_id)
    print("A visual match is not authentication, identity proof, or authorization.")


if __name__ == "__main__":
    main()
