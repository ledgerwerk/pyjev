from pyjev import credentials


def test_env_precedes_keyring(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", " env-key ")
    monkeypatch.setattr(credentials.keyring, "get_password", lambda *args: "keyring-key")
    assert credentials.get_api_key() == "env-key"
    assert credentials.credential_source() == "environment"


def test_explicit_precedes_env(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "env-key")
    assert credentials.get_api_key(" explicit ") == "explicit"
