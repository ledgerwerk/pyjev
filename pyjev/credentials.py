"""API-key lookup and keyring or user-file storage."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE_NAME = "pyjev"
USERNAME = "typesafe-api-key"
ENV_NAME = "TYPESAFE_API_KEY"


class CredentialError(RuntimeError):
    """Credential storage or retrieval failed."""


def _nonempty(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def credential_file_path() -> Path:
    """Return the user-level plaintext credential path."""
    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        base = Path(xdg).expanduser()
        if base.is_absolute():
            return base / "pyjev" / "credentials"
    return Path.home() / ".config" / "pyjev" / "credentials"


def _read_file_api_key() -> str | None:
    path = credential_file_path()
    try:
        return _nonempty(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CredentialError(f"Could not read credential file {path}: {exc}") from exc


def get_api_key(explicit: str | None = None) -> str | None:
    """Resolve an API key: explicit argument, environment, keyring, then file."""
    if key := _nonempty(explicit):
        return key
    if key := _nonempty(os.getenv(ENV_NAME)):
        return key
    try:
        if key := _nonempty(keyring.get_password(SERVICE_NAME, USERNAME)):
            return key
    except KeyringError:
        pass
    return _read_file_api_key()


def set_api_key(api_key: str) -> None:
    """Store an API key in the OS keyring only."""
    key = _nonempty(api_key)
    if key is None:
        raise CredentialError("API key cannot be empty.")
    try:
        keyring.set_password(SERVICE_NAME, USERNAME, key)
    except KeyringError as exc:
        raise CredentialError(f"Could not store the API key in the OS keyring: {exc}") from exc


def set_file_api_key(api_key: str) -> Path:
    """Store an API key in the user-level plaintext credential file."""
    key = _nonempty(api_key)
    if key is None:
        raise CredentialError("API key cannot be empty.")

    path = credential_file_path()
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                path.parent.chmod(0o700)
            except OSError:
                pass

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            if os.name != "nt":
                try:
                    temporary_path.chmod(0o600)
                except OSError:
                    pass
            temporary.write(f"{key}\n")
            temporary.flush()
            os.fsync(temporary.fileno())

        os.replace(temporary_path, path)
        temporary_path = None
        if os.name != "nt":
            try:
                path.chmod(0o600)
            except OSError:
                pass
    except OSError as exc:
        raise CredentialError(f"Could not store the API key in {path}: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass
    return path


def _delete_file_api_key() -> bool:
    path = credential_file_path()
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise CredentialError(f"Could not delete credential file {path}: {exc}") from exc


def delete_api_key() -> bool:
    """Delete all pyjev-managed persisted credentials."""
    keyring_removed = False
    keyring_error: KeyringError | None = None
    try:
        keyring.delete_password(SERVICE_NAME, USERNAME)
        keyring_removed = True
    except PasswordDeleteError:
        pass
    except KeyringError as exc:
        keyring_error = exc

    file_removed = _delete_file_api_key()
    if keyring_error is not None and not file_removed:
        raise CredentialError(f"Could not access the OS keyring: {keyring_error}") from keyring_error
    return keyring_removed or file_removed


def credential_source() -> str:
    """Return the effective persisted/environment credential source."""
    if _nonempty(os.getenv(ENV_NAME)):
        return "environment"
    try:
        if _nonempty(keyring.get_password(SERVICE_NAME, USERNAME)):
            return "keyring"
    except KeyringError:
        pass
    if _read_file_api_key() is not None:
        return "file"
    return "missing"
