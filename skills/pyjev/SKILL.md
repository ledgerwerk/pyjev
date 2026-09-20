---
name: pyjev
description: Inspect, validate, compile, and safely execute named pyjev decision contracts.
---

# pyjev agent workflow

Use this skill when a project contains `.pyjev.toml` or asks an agent to use
pyjev. Prefer the named-decision contract over re-spelling stable criteria in a
prompt or one-off command.

## Inspect before execution

Run these commands from the project directory:

```bash
pyjev decision list --json
pyjev decision show DECISION --json
pyjev decision validate
pyjev decision compile DECISION --state '...'
```

Validation and compilation are offline. They do not need credentials and do not
contact the Jev API. Inspect the compiled request, schema marker, and
specification fingerprint before executing a decision.

## Execute deliberately

Execute only after validation and offline compilation succeed:

```bash
echo '...' | pyjev decide DECISION --json
```

Use `--config` when the declaration is not found by normal discovery. Preserve
the full JSON result when uncertainty, probabilities, usage, model, or request
ID matters. Do not flatten a result to `--value` unless downstream automation
is safe to consume a scalar.

For Choice and Score, use an explicit application threshold when automation
needs a confidence policy:

```bash
pyjev decide DECISION --min-confidence 0.85 --value
```

A valid result below the threshold exits `3` and emits no actionable value on
stdout. Treat that as a human-review path, not as an API or authentication
failure.

## Keep deterministic logic in code

Use normal Python for exact rules, legal-action filtering, permissions, and
other deterministic constraints. Use a named Jev decision for a stable
judgment contract. If criteria are dynamic, build them with `Jev` or
`AsyncJev` after deterministic filtering.

## Credential safety

Do not place keys in `.pyjev.toml`, prompts, skill files, command arguments, or
logs. Prefer `TYPESAFE_API_KEY` in automation and hidden `pyjev auth set` input
for local setup. Use `pyjev auth test --json` to verify the active credential;
it performs one request and returns safe metadata only.

## Failure handling

- Exit `2`: fix usage or local validation before retrying.
- Exit `1`: inspect safe runtime, credential, API, network, or I/O diagnostics.
- Exit `3`: route the valid but below-policy result to review.

These are pyjev-specific codes and must not be assumed to match another `jev`
CLI. Never retry a low-confidence result as if it were a transport error.
