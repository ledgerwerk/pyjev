from pathlib import Path

import pytest
from keyring.errors import KeyringError, PasswordDeleteError

from pyjev import credentials


@pytest.fixture(autouse=True)
def isolate_keyring(monkeypatch):
    monkeypatch.setattr(credentials.keyring, "get_password", lambda *args: None)
    monkeypatch.setattr(credentials.keyring, "set_password", lambda *args: None)
    monkeypatch.setattr(
        credentials.keyring,
        "delete_password",
        lambda *args: (_ for _ in ()).throw(PasswordDeleteError()),
    )


def set_config_home(monkeypatch, tmp_path):
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    return config_home / "pyjev" / "credentials"


def test_env_precedes_keyring(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", " env-key ")
    monkeypatch.setattr(credentials.keyring, "get_password", lambda *args: "keyring-key")
    assert credentials.get_api_key() == "env-key"
    assert credentials.credential_source() == "environment"


def test_explicit_precedes_env_and_persisted_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "env-key")
    path = set_config_home(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("file-key\n", encoding="utf-8")
    monkeypatch.setattr(credentials.keyring, "get_password", lambda *args: "keyring-key")
    assert credentials.get_api_key(" explicit ") == "explicit"


def test_keyring_beats_file(monkeypatch, tmp_path):
    path = set_config_home(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("file-key\n", encoding="utf-8")
    monkeypatch.setattr(credentials.keyring, "get_password", lambda *args: "keyring-key")
    assert credentials.get_api_key() == "keyring-key"
    assert credentials.credential_source() == "keyring"


def test_file_is_read_when_keyring_returns_none(monkeypatch, tmp_path):
    path = set_config_home(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(" file-key \n", encoding="utf-8")
    assert credentials.get_api_key() == "file-key"


def test_file_is_read_when_keyring_raises(monkeypatch, tmp_path):
    path = set_config_home(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("file-key\n", encoding="utf-8")
    monkeypatch.setattr(
        credentials.keyring,
        "get_password",
        lambda *args: (_ for _ in ()).throw(KeyringError("broken")),
    )
    assert credentials.get_api_key() == "file-key"


def test_credential_file_path_respects_absolute_xdg(monkeypatch, tmp_path):
    config_home = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    assert credentials.credential_file_path() == config_home / "pyjev" / "credentials"


def test_writer_creates_parent_and_uses_single_line_format(monkeypatch, tmp_path):
    path = set_config_home(monkeypatch, tmp_path)
    returned = credentials.set_file_api_key("  file-key  ")
    assert returned == path
    assert path.read_text(encoding="utf-8") == "file-key\n"
    assert path.parent.is_dir()


def test_writer_uses_restrictive_posix_mode(monkeypatch, tmp_path):
    path = set_config_home(monkeypatch, tmp_path)
    credentials.set_file_api_key("file-key")
    if path.stat().st_mode:
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700


def test_empty_key_is_rejected_consistently(monkeypatch, tmp_path):
    set_config_home(monkeypatch, tmp_path)
    with pytest.raises(credentials.CredentialError, match="cannot be empty"):
        credentials.set_api_key("  ")
    with pytest.raises(credentials.CredentialError, match="cannot be empty"):
        credentials.set_file_api_key("  ")


def test_empty_file_is_not_a_credential(monkeypatch, tmp_path):
    path = set_config_home(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(" \n", encoding="utf-8")
    assert credentials.get_api_key() is None
    assert credentials.credential_source() == "missing"


def test_delete_removes_file_even_when_keyring_raises(monkeypatch, tmp_path):
    path = set_config_home(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("file-key\n", encoding="utf-8")
    monkeypatch.setattr(
        credentials.keyring,
        "delete_password",
        lambda *args: (_ for _ in ()).throw(KeyringError("broken")),
    )
    assert credentials.delete_api_key() is True
    assert not path.exists()


def test_delete_returns_false_when_nothing_is_stored(monkeypatch, tmp_path):
    set_config_home(monkeypatch, tmp_path)
    assert credentials.delete_api_key() is False


def test_credential_source_reports_file(monkeypatch, tmp_path):
    path = set_config_home(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("file-key\n", encoding="utf-8")
    assert credentials.credential_source() == "file"


def test_unreadable_file_raises_without_exposing_contents(monkeypatch, tmp_path):
    path = set_config_home(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("super-secret-key\n", encoding="utf-8")

    def unreadable(*args, **kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "read_text", unreadable)
    with pytest.raises(credentials.CredentialError) as error:
        credentials.get_api_key()
    assert str(path) in str(error.value)
    assert "super-secret-key" not in str(error.value)
