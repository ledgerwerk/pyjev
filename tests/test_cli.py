from typer.testing import CliRunner

import pyjev.cli as cli
from pyjev.cli import app
from pyjev.credentials import CredentialError

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


def test_auth_set_prompts_and_stores_in_working_keyring(monkeypatch, tmp_path):
    stored = []
    monkeypatch.setattr(cli, "set_api_key", lambda key: stored.append(key))
    monkeypatch.setattr(cli, "credential_file_path", lambda: tmp_path / "credentials")
    monkeypatch.setattr(cli, "set_file_api_key", lambda key: (_ for _ in ()).throw(AssertionError("file fallback")))

    result = runner.invoke(app, ["auth", "set", "--storage", "keyring"], input="secret-key\n")

    assert result.exit_code == 0
    assert stored == ["secret-key"]
    assert "Stored TypeSafe API key in the OS keyring." in result.output
    assert not (tmp_path / "credentials").exists()


def test_auth_set_broken_keyring_interactive_accepts_file_fallback(monkeypatch, tmp_path):
    path = tmp_path / "credentials"
    monkeypatch.setattr(cli, "credential_file_path", lambda: path)
    monkeypatch.setattr(
        cli,
        "set_api_key",
        lambda key: (_ for _ in ()).throw(
            CredentialError(
                "Could not store the API key in the OS keyring: backend unavailable.",
            )
        ),
    )
    written = []

    def write_file(key):
        written.append(key)
        path.write_text(key + "\n", encoding="utf-8")
        return path

    monkeypatch.setattr(cli, "set_file_api_key", write_file)
    result = runner.invoke(app, ["auth", "set"], input="secret-key\ny\n")

    assert result.exit_code == 0
    assert written == ["secret-key"]
    assert "backend unavailable." in result.output
    assert "plaintext" in result.output
    assert "Store the API key there?" in result.output
    assert "Stored TypeSafe API key in" in result.output
    assert "secret-key" not in result.output


def test_auth_set_broken_keyring_interactive_decline_does_not_write(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "credential_file_path", lambda: tmp_path / "credentials")
    monkeypatch.setattr(
        cli,
        "set_api_key",
        lambda key: (_ for _ in ()).throw(CredentialError("keyring unavailable")),
    )
    monkeypatch.setattr(cli, "set_file_api_key", lambda key: (_ for _ in ()).throw(AssertionError("file fallback")))

    result = runner.invoke(app, ["auth", "set"], input="secret-key\nn\n")

    assert result.exit_code == 1
    assert "API key was not stored" in result.output
    assert not (tmp_path / "credentials").exists()
    assert "secret-key" not in result.output


def test_auth_set_explicit_key_after_keyring_failure_never_confirms(monkeypatch):
    monkeypatch.setattr(
        cli,
        "set_api_key",
        lambda key: (_ for _ in ()).throw(CredentialError("keyring unavailable")),
    )

    def fail_confirm(*args, **kwargs):
        raise AssertionError("unexpected confirmation")

    monkeypatch.setattr(cli.typer, "confirm", fail_confirm)

    result = runner.invoke(app, ["auth", "set", "--api-key", "secret-key"])

    assert result.exit_code == 1
    assert "--storage file" in result.output
    assert "secret-key" not in result.output


def test_auth_set_explicit_file_storage_warns_and_never_calls_keyring(monkeypatch, tmp_path):
    path = tmp_path / "credentials"
    stored = []
    monkeypatch.setattr(cli, "credential_file_path", lambda: path)
    monkeypatch.setattr(cli, "set_api_key", lambda key: (_ for _ in ()).throw(AssertionError("keyring call")))
    monkeypatch.setattr(cli, "set_file_api_key", lambda key: stored.append(key) or path)

    result = runner.invoke(app, ["auth", "set", "--api-key", "secret-key", "--storage", "file"])

    assert result.exit_code == 0
    assert stored == ["secret-key"]
    assert "plaintext" in result.output
    assert "Stored TypeSafe API key in" in result.output
    assert "secret-key" not in result.output


def test_auth_set_keyring_mode_does_not_fallback(monkeypatch):
    monkeypatch.setattr(
        cli,
        "set_api_key",
        lambda key: (_ for _ in ()).throw(CredentialError("keyring unavailable")),
    )
    monkeypatch.setattr(cli, "set_file_api_key", lambda key: (_ for _ in ()).throw(AssertionError("file fallback")))

    result = runner.invoke(app, ["auth", "set", "--api-key", "secret-key", "--storage", "keyring"])

    assert result.exit_code == 1
    assert "keyring unavailable" in result.output
    assert "plaintext" not in result.output
    assert "secret-key" not in result.output


def test_auth_status_reports_file_source(monkeypatch, tmp_path):
    path = tmp_path / "credentials"
    monkeypatch.setattr(cli, "credential_source", lambda: "file")
    monkeypatch.setattr(cli, "credential_file_path", lambda: path)

    result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    assert f"API key stored in {path} (plaintext file)." in result.output


def test_auth_delete_reports_active_environment(monkeypatch):
    monkeypatch.setattr(cli, "delete_api_key", lambda: True)
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret-key")

    result = runner.invoke(app, ["auth", "delete"])

    assert result.exit_code == 0
    assert "Deleted stored API key." in result.output
    assert "TYPESAFE_API_KEY is still set and remains the active credential." in result.output
    assert "secret-key" not in result.output


def test_auth_status_handles_credential_file_error(monkeypatch):
    monkeypatch.setattr(
        cli,
        "credential_source",
        lambda: (_ for _ in ()).throw(CredentialError("Could not read credential file /tmp/x: denied")),
    )

    result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 1
    assert "Could not read credential file" in result.output
