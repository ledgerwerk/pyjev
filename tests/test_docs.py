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
        "patterns.md",
        "confidence.md",
        "authentication.md",
        "agent-skill.md",
        "debugging.md",
        "examples.md",
        "recipes.md",
        "comparisons.md",
        "development.md",
        "changelog.md",
    }
    assert expected <= {path.name for path in (ROOT / "docs").iterdir()}
    script = (ROOT / "docs" / "make.py").read_text(encoding="utf-8")
    assert "Path(__file__).resolve().parents[1]" in script
    assert '"-m",\n        "sphinx"' in script
    assert '"-W"' in script


def test_documentation_emphasizes_decision_contracts_and_boundaries() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    comparison = (ROOT / "docs" / "comparisons.md").read_text(encoding="utf-8")
    skill = (ROOT / "skills" / "pyjev" / "SKILL.md").read_text(encoding="utf-8")
    patterns = (ROOT / "docs" / "patterns.md").read_text(encoding="utf-8")
    recipes = (ROOT / "docs" / "recipes.md").read_text(encoding="utf-8")
    examples = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    assert readme.index("decision contracts") < readme.index("Direct dynamic decisions")
    assert "`typesafe-sdk`" in readme
    assert "official" in readme
    assert "version **0.6.2**" in comparison
    assert "not interchangeable" in comparison
    assert "pyjev decision compile" in skill
    assert "confidence" in skill.lower()
    assert "docs/patterns.md" in readme
    assert "Intent routing" in patterns
    assert "Composite scoring" in patterns
    assert "Confidence-gated routing" in patterns
    assert "Speculative fan-out" in patterns
    assert "## Classify" in recipes
    assert "## Match" in recipes
    assert "## Route" in recipes and "never calls `application_dispatch`" in recipes
    assert "## Rerank" in recipes
    assert "## Screen" in recipes and "security boundary" in recipes
    assert "support_triage.py" in examples
