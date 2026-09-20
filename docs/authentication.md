# Authentication

Credential lookup order for Python clients is:

1. explicit Python `api_key=`;
2. `TYPESAFE_API_KEY`;
3. the OS keyring;
4. a user-level plaintext fallback file.

Decision validation and compilation do not read credentials or contact the Jev
API.

## CLI management

For interactive local setup, omit the key argument so input stays hidden:

```bash
pyjev auth set
pyjev auth status
pyjev auth test
```

`auth test` performs exactly one minimal request through the official SDK. It
reports only the credential source and returned model:

```text
credential: keyring
status: valid
model: jev-latest
```

Use `--json` for automation:

```bash
pyjev auth test --json
```

```json
{ "credential_source": "keyring", "model": "jev-latest", "ok": true }
```

Missing credentials, authentication rejection, network failures, and API
failures use runtime exit code `1` and safe status messages. The command never
persists a credential and never prints the key.

The explicit `--api-key` option remains available for compatibility:

```bash
pyjev auth set --api-key '...'
```

It is **unsafe** because shell history, process listings, or CI command logs may
expose the value. Prefer the hidden prompt for interactive use and
`TYPESAFE_API_KEY` for non-interactive use. If a secret must be supplied by a
pipeline, keep it in the environment or protected stdin rather than command
arguments.

```bash
export TYPESAFE_API_KEY='...'
pyjev auth test --json
```

`pyjev auth delete` removes pyjev-managed persisted credentials but does not
unset an active `TYPESAFE_API_KEY` environment variable.

:::{warning}
`--storage file` stores the key as plaintext in the user's configuration
directory. Restrictive permissions are helpful but do not make the key
encrypted.
:::

## Credential sources

`auth status` identifies the effective source as `environment`, `keyring`, or
`file`. It reports `missing` as an error. Errors, JSON output, and diagnostic
messages must not include the key contents.

Project `.pyjev.toml` files must never contain API keys. Keep credentials out of
source control, compiled decision previews, documentation builds, and logs.
