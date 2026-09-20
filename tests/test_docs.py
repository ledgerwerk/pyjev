from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_documentation_tree_and_build_script_are_present() -> None:
    expected = {
        "index.md",
        "getting-started.md",
        "concepts.md",
        "python-api.md",
        "cli.md",
        "named-decisions.md",
        "confidence.md",
        "authentication.md",
        "debugging.md",
        "examples.md",
        "comparisons.md",
        "development.md",
        "changelog.md",
    }
    assert expected <= {path.name for path in (ROOT / "docs").iterdir()}
    script = (ROOT / "docs" / "make.py").read_text(encoding="utf-8")
    assert "Path(__file__).resolve().parents[1]" in script
    assert '"-m",\n        "sphinx"' in script
    assert '"-W"' in script
