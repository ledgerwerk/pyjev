"""API-key lookup and keyring storage."""

from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE_NAME = "pyjev"
USERNAME = "typesafe-api-key"
ENV_NAME = "TYPESAFE_API_KEY"


class CredentialError(RuntimeError):
    """Credential storage failed."""


def _nonempty(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def get_api_key(explicit: str | None = None) -> str | None:
    """Resolve an API key: explicit argument, environment, then OS keyring."""
    if key := _nonempty(explicit):
        return key
    if key := _nonempty(os.getenv(ENV_NAME)):
        return key
    try:
        return _nonempty(keyring.get_password(SERVICE_NAME, USERNAME))
    except KeyringError:
        return None


def set_api_key(api_key: str) -> None:
    key = _nonempty(api_key)
    if key is None:
        raise CredentialError("API key cannot be empty.")
    try:
        keyring.set_password(SERVICE_NAME, USERNAME, key)
    except KeyringError as exc:
        raise CredentialError(f"Could not store the API key in the OS keyring: {exc}. Set {ENV_NAME} instead.") from exc


def delete_api_key() -> bool:
    try:
        keyring.delete_password(SERVICE_NAME, USERNAME)
        return True
    except PasswordDeleteError:
        return False
    except KeyringError as exc:
        raise CredentialError(f"Could not access the OS keyring: {exc}") from exc


def credential_source() -> str:
    if _nonempty(os.getenv(ENV_NAME)):
        return "environment"
    try:
        if _nonempty(keyring.get_password(SERVICE_NAME, USERNAME)):
            return "keyring"
    except KeyringError:
        return "missing"
    return "missing"
