from typer.testing import CliRunner

from pyjev.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip()


def test_choice_requires_two_options():
    result = runner.invoke(
        app,
        ["choice", "Route?", "--state", "x", "--option", "only-one"],
    )
    assert result.exit_code != 0
    assert "at least two" in result.output
