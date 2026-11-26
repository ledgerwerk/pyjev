"""Locate a target in an image and ask a companion question about its presence."""

from __future__ import annotations

import argparse
from pathlib import Path

from pyjev import Image, Jev

CONFIG = Path(__file__).with_name(".pyjev.toml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="path to a PNG or JPEG image")
    parser.add_argument("--width", type=int, help="optional source image width in pixels")
    parser.add_argument("--height", type=int, help="optional source image height in pixels")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if (args.width is None) != (args.height is None):
        raise SystemExit("--width and --height must be supplied together")

    with Jev(images=True) as jev:
        result = jev.decide(
            "mug-localization",
            state={"photo": Image(args.image)},
            config=CONFIG,
        )

    presence = result.answers["visible"]
    location = result.answers["location"]
    print("presence probability:", presence.value)
    print("normalized box:", location.box)
    print("box confidence:", location.confidence)
    if args.width is not None and args.height is not None:
        box = location.box
        pixels = (
            round(box["left"] * args.width),
            round(box["top"] * args.height),
            round(box["right"] * args.width),
            round(box["bottom"] * args.height),
        )
        print("pixel edges (left, top, right, bottom):", pixels)
    print("A Box result is not a not-found signal. Interpret the companion Noul in application policy.")


if __name__ == "__main__":
    main()
