# Getting started

This walkthrough introduces pyjev's main idea: define a reusable decision
contract, inspect it offline, then use the same contract from shell and Python.

## Install

```bash
pip install pyjev
uv tool install pyjev
```

For a checkout, install contributor and documentation dependencies separately:

```bash
pip install -e '.[dev,docs]'
```

## Create a decision contract

In a project directory, create `.pyjev.toml`:

```toml
[pyjev]
schema = 1

[decision.ticket-route]
type = "choice"
question = "Which team should handle this support request?"

[decision.ticket-route.options]
billing = "Billing, invoice, payment, or refund issue"
engineering = "Technical problem or product bug"
sales = "Purchasing, pricing, or procurement question"
```

This is a version-controlled specification. It is not a secret store and must
not contain API keys.

## Inspect before execution

Validation and compilation are local operations:

```bash
pyjev decision validate
pyjev decision show ticket-route
pyjev decision compile ticket-route --state "Stripe webhooks fail"
```

They do not read credentials, construct a client, or contact the Jev API. The
compiled output is a normalized request preview with a stable schema marker and
non-secret decision fingerprint.

## Authenticate

For an interactive local setup, use hidden input:

```bash
pyjev auth set
pyjev auth status
pyjev auth test
```

For CI, prefer the environment:

```bash
export TYPESAFE_API_KEY='...'
pyjev auth test --json
```

`auth test` performs one minimal request through the official SDK and reports
safe metadata only. The explicit `auth set --api-key` option is retained for
compatibility but is unsafe because shell history and process listings may
expose the value. Do not put secrets in command output, decision files, or
logs.

:::{warning}
The file fallback is plaintext. Restrictive permissions reduce exposure but do
not encrypt the credential.
:::

## Execute from shell

```bash
echo "Stripe webhooks fail" | pyjev decide ticket-route --json
```

`--json` preserves result metadata. Use `--value` only when a scalar is safe to
consume, and use `--min-confidence` when the application requires a confidence
policy.

## Execute from Python

```python
from pyjev import Jev

with Jev() as jev:
    result = jev.decide("ticket-route", state="Stripe webhooks fail")

print(result.value)
print(result.confidence)
print(result.probabilities)
```

For native asynchronous applications:

```python
from pyjev import AsyncJev

async with AsyncJev() as jev:
    result = await jev.decide("ticket-route", state="Stripe webhooks fail")
```

## When to use a direct primitive

Use `jev.choice(...)`, `jev.noul(...)`, or `jev.score(...)` when criteria are
computed dynamically from deterministic application state. Keep deterministic
constraints in normal Python; use a named decision when the judgment contract
is stable and worth reviewing in source control.

Continue with [Named decisions](named-decisions.md), [Confidence](confidence.md),
[Authentication](authentication.md), and [Python API](python-api.md).
