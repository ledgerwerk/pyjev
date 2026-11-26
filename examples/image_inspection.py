"""Classify the primary subject in a caller-supplied image.

For localization and a companion presence judgment, see image_localization.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pyjev import Image, Jev


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="path to a PNG or JPEG image")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with Jev(images=True) as jev:
        result = jev.choice(
            "Which category best describes `photo`?",
            state={"photo": Image(args.image)},
            choices={
                "person": "A person is the primary subject.",
                "package": "A parcel, box, or package is the primary subject.",
                "vehicle": "A vehicle is the primary subject.",
                "other": "None of the above.",
            },
        )

    print("choice:", result.value)
    print("confidence:", result.confidence)
    print("probabilities:", result.probabilities)
    print("These categories are an example, not an exhaustive real-world policy.")


if __name__ == "__main__":
    main()
