# pyjev

**Confidence-aware Jev decisions for Python, shell, CI, and automation.**

pyjev is a thin operational layer over TypeSafe's official `typesafe-sdk`. It
preserves Jev probabilities, confidence, and response metadata while adding
reusable named decisions, shell-safe output, local validation, request
inspection, and credential ergonomics.

## CLI

```bash
pyjev choice "Where should this ticket go?" \
  --state "Stripe checkout fails" \
  --option billing="Payments and refunds" \
  --option engineering="Technical failures" \
  --option sales="Purchasing questions"
```

## Python

```python
from pyjev import Jev

with Jev() as jev:
    result = jev.choice(
        "Where should this ticket go?",
        state="Stripe checkout fails",
        choices={"billing": "Payments", "engineering": "Technical", "sales": "Purchasing"},
    )

print(result.value)
print(result.confidence)
print(result.probabilities)
```

## Why pyjev?

- Preserve probabilities, confidence, and response metadata.
- Define reusable decisions in `.pyjev.toml`.
- Use the same decision from Python or the shell.
- Gate automation explicitly at the invocation boundary.
- Validate mistakes before spending an API request.
- Retain request IDs and usage metadata for debugging.

Start with [Getting started](getting-started.md), then read [Concepts](concepts.md).
See [Confidence](confidence.md) for safe automation, [Named decisions](named-decisions.md)
for reusable specifications, [CLI](cli.md) for shell usage, and [Python API](python-api.md)
for code usage.

```{toctree}
:maxdepth: 2
:hidden:

getting-started
concepts
python-api
cli
named-decisions
confidence
authentication
debugging
examples
comparisons
api/index
development
changelog
```
