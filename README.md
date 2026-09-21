[![PyPI - Version](https://img.shields.io/pypi/v/pyjev)](https://pypi.org/project/pyjev/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pyjev)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pyjev)
[![codecov](https://codecov.io/gh/ledgerwerk/pyjev/graph/badge.svg?token=34W6LDpSJB)](https://codecov.io/gh/ledgerwerk/pyjev)

# pyjev

**Reusable, inspectable Jev decision contracts for Python applications and automation.**

`pyjev` is a Python-first operational layer over TypeSafe's official
`typesafe-sdk`. It gives applications typed sync and native async APIs, reusable
version-controlled `.pyjev.toml` decisions, offline validation and request
compilation, preserved uncertainty, credential ergonomics, and explicit
confidence-gated automation.

## Why pyjev?

- **Python integration:** dependency injection, caller-owned SDK clients, lifecycle semantics, and typed result wrappers.
- **Decision contracts:** declare named Noul, Choice, Score, and bundle decisions once in `.pyjev.toml`, then reuse them from Python and shell.
- **Offline inspection:** validate and compile a decision without credentials, client construction, or network access.
- **Uncertainty preserved:** probabilities, confidence, usage, request IDs, and raw answer metadata remain available to callers.
- **Application policy:** confidence gates make the caller's automation threshold explicit and shell-safe.
- **Official transport boundary:** TypeSafe's SDK owns API models, transport, retries, authentication, and API semantics; pyjev adds application-level structure.

## Decision patterns

`pyjev` supports intent routing, composite scoring, confidence-gated automation, and speculative fan-out by combining typed Jev questions with explicit Python policy. Named bundles evaluate several independent questions about one state in a single request, and result wrappers preserve each answer's uncertainty so application code can gate, combine, ignore, or route deterministically.

Keep normalization and weights in application code. Gate the result that controls the action. A bundle deliberately has no aggregate confidence because its child judgments can have different uncertainty and consequences. See the [decision patterns guide](docs/patterns.md) and run `python examples/support_triage.py` for a combined example.

The `pyjev` command is an interface to these library and decision-contract
capabilities. It is useful in shell and CI, but direct primitive commands are
not the whole product.

## A 60-second named decision

Create a version-controlled `.pyjev.toml`:

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

Inspect it before using credentials or the network:

```bash
pyjev decision validate
pyjev decision compile ticket-route --state "Stripe checkout fails"
```

Execute the same named contract from shell:

```bash
echo 'Stripe checkout fails' | pyjev decide ticket-route --json
```

Or from Python:

```python
from pyjev import Jev

with Jev() as jev:
    result = jev.decide("ticket-route", state="Stripe checkout fails")


For local result and policy composition, use the optional pipeline stages without hiding the network call:

```python
from pyjev.pipeline import require_confidence

policy = require_confidence(0.70)
outcome = result | policy
if outcome.passed:
    route_to(outcome.value)
else:
    human_review(outcome.result)
```

The pipe operates only on an already returned result. It does not execute handlers or turn model output into an action.
print(result.value, result.confidence, result.probabilities)
```

For async applications, use the native SDK-backed API:

```python
from pyjev import AsyncJev

async with AsyncJev() as jev:
    result = await jev.decide("ticket-route", state="Stripe checkout fails")
```

## Direct dynamic decisions

When criteria are inherently runtime-dependent, use the typed Python API or the
CLI directly:

```bash
pyjev choice "Where should this ticket go?" \
  --state "Stripe checkout fails" \
  --option billing="Payments and refunds" \
  --option engineering="Technical failures" \
  --option sales="Purchasing questions" \
  --json
```

```python
from pyjev import Jev

with Jev() as jev:
    result = jev.choice(
        "Where should this ticket go?",
        state="Stripe checkout fails",
        choices={"billing": "Payments", "engineering": "Technical", "sales": "Purchasing"},
    )

print(result.value, result.confidence, result.probabilities)
```

## Confidence-aware automation

Choice and Score can require an application-selected threshold:

```bash
pyjev choice "Route this ticket" \
  --option billing --option engineering --option sales \
  --min-confidence 0.85 --value
```

A valid result below the threshold exits with pyjev's code `3` and emits no
actionable `--value` stdout. Confidence is a Jev signal; the threshold is the
caller's policy, not a universal correctness probability.

## Authentication

Use the hidden interactive prompt for local setup or `TYPESAFE_API_KEY` in CI:

```bash
pyjev auth set
pyjev auth test
export TYPESAFE_API_KEY='...'
```

`pyjev auth test` performs one minimal official-SDK request and reports safe
credential-source and model metadata. Do not put secrets in `.pyjev.toml`.
The explicit `auth set --api-key` option remains available for compatibility but
is unsafe because shell history and process inspection may expose it.

## pyjev, the official SDK, and jev-cli

- Use `typesafe-sdk` directly for low-level TypeSafe control.
- Use `pyjev` for Python application integration, named decision contracts,
  offline tooling, typed uncertainty, and confidence-aware policy.
- Use a standalone provider-aware CLI/MCP tool such as `jev-cli` for its direct
  shell, provider, MCP, and agent-skill workflows.

These tools overlap on primitive shell operations but optimize for different
layers. See [the comparison](docs/comparisons.md) for the dated feature matrix.

## Install

```bash
pip install pyjev
# or
uv tool install pyjev
```

For a development checkout:

```bash
pip install -e '.[dev,docs]'
```

## Learn more

- [Full documentation](docs/index.md)
- [Getting started](docs/getting-started.md)
- [Named decisions](docs/named-decisions.md)
- [Python API](docs/python-api.md)
- [CLI and exit codes](docs/cli.md)
- [Agent skill](docs/agent-skill.md)
- [Runnable examples](examples/README.md)
- [TypeSafe Jev documentation](https://docs.typesafe.ai/)

## License

Apache-2.0
