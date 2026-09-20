#!/usr/bin/env python3
"""Build pyjev documentation with the active Python environment."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
BUILD = DOCS / "_build"
TARGETS = {"html", "dirhtml", "text", "linkcheck", "doctest"}


def run(builder: str) -> int:
    output = BUILD / builder
    command = [
        sys.executable,
        "-m",
        "sphinx",
        "-W",
        "--keep-going",
        "-b",
        builder,
        str(DOCS),
        str(output),
    ]
    print(f"Building {builder} documentation...")
    subprocess.run(command, cwd=ROOT, check=True)
    print(f"Build finished. Documentation is in {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    target = (argv or sys.argv[1:] or ["html"])[0]
    if target == "help":
        print(__doc__)
        print("Targets: clean, html, dirhtml, text, linkcheck, doctest, all")
        return 0
    if target == "clean":
        if BUILD.exists():
            shutil.rmtree(BUILD)
        return 0
    if target == "all":
        for builder in ("html", "text", "linkcheck"):
            run(builder)
        return 0
    if target not in TARGETS:
        print(f"Unknown target: {target}", file=sys.stderr)
        print("Use 'help' target for help", file=sys.stderr)
        return 1
    return run(target)


if __name__ == "__main__":
    raise SystemExit(main())
