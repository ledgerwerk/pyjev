from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_documentation_tree_and_build_script_are_present() -> None:
    expected = {
        "index.md",
        "why-pyjev.md",
        "getting-started.md",
        "concepts.md",
        "python-api.md",
        "images.md",
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
    assert readme.index("decision contracts") < readme.index("When a named contract is not the right abstraction")
    assert "`typesafe-sdk`" in readme
    assert "official" in readme
    assert "version **0.6.2**" in comparison
    assert "not interchangeable" in comparison
    assert "pyjev decision compile" in skill
    assert "confidence" in skill.lower()
    assert "docs/recipes.md" in readme
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


def test_why_pyjev_page_and_cross_links_explain_the_product_boundary() -> None:
    why = (ROOT / "docs" / "why-pyjev.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    index = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    getting_started = (ROOT / "docs" / "getting-started.md").read_text(encoding="utf-8")
    comparison = (ROOT / "docs" / "comparisons.md").read_text(encoding="utf-8")
    agent_guidance = (ROOT / "docs" / "agent-skill.md").read_text(encoding="utf-8")
    skill = (ROOT / "skills" / "pyjev" / "SKILL.md").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "decision contract" in why.lower()
    assert "offline" in why.lower() and "fingerprint" in why.lower()
    assert "shell" in why.lower() and "python" in why.lower()
    assert "caller" in why.lower() and "policy" in why.lower()
    assert "recipes" in why.lower()
    assert "box" in why.lower()
    assert "typesafe-sdk" in why
    assert "Use `typesafe-sdk` directly" in why
    assert "[Why pyjev?](docs/why-pyjev.md)" in readme
    assert "why-pyjev" in index
    assert "[Why pyjev?](why-pyjev.md)" in getting_started
    assert "[Why pyjev?](why-pyjev.md)" in comparison
    assert "[Why pyjev?](why-pyjev.md)" in agent_guidance
    assert "Use `typesafe-sdk` directly" in skill
    assert "Do not reimplement SDK transport" in skill
    assert "calling `typesafe-sdk` directly may be simpler" in readme
    assert "Intentionally delegated to the SDK" in comparison
    assert 'readme = "README.md"' in project


def test_readme_fenced_code_blocks_are_balanced() -> None:
    opening: tuple[str, int, int] | None = None
    for line_number, line in enumerate((ROOT / "README.md").read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.lstrip()
        if not stripped or stripped[0] not in "`~":
            continue
        marker = stripped[0]
        marker_length = len(stripped) - len(stripped.lstrip(marker))
        if marker_length < 3:
            continue
        if opening is None:
            opening = (marker, marker_length, line_number)
        elif marker == opening[0] and marker_length >= opening[1]:
            opening = None

    assert opening is None, f"Unclosed Markdown fence opened at README.md:{opening[2] if opening else '?'}"


def test_image_documentation_covers_opt_in_and_experimental_status() -> None:
    images = (ROOT / "docs" / "images.md").read_text(encoding="utf-8")
    index = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    assert "TypeSafe-Danger-Zone-Images" in images
    assert "dreamer-ready" in images.lower()
    assert "assets=" in images
    assert "images" in index
