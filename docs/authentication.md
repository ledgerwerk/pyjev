# Authentication

Credential lookup order is:

1. explicit Python `api_key=`;
2. `TYPESAFE_API_KEY`;
3. the OS keyring;
4. a user-level plaintext fallback file.

## CLI management

```bash
pyjev auth set
pyjev auth set --storage keyring
pyjev auth set --storage file
pyjev auth status
pyjev auth delete
```

Interactive entry hides the key. `--api-key SECRET` can leak into shell history, so use
it only when that tradeoff is acceptable. Deleting persisted credentials does not unset
an active `TYPESAFE_API_KEY` environment variable.

:::{warning}
`--storage file` stores the key as plaintext in the user's configuration directory.
Restrictive permissions are helpful but do not make the key encrypted.
:::

Project `.pyjev.toml` files must never contain API keys. Decision compilation and docs
builds do not read credentials or contact the Jev API.
