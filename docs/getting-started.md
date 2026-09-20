# Getting started

This page takes a new user from installation to a first decision in about five minutes.

## Install

```bash
pip install pyjev
uv tool install pyjev
```

For a checkout, install contributor and documentation dependencies separately:

```bash
pip install -e '.[dev,docs]'
```

## Authenticate

For an interactive local setup:

```bash
pyjev auth set
pyjev auth status
```

For CI, use an environment variable:

```bash
export TYPESAFE_API_KEY='...'
```

:::{warning}
The file fallback is plaintext. Restrictive permissions reduce exposure but do not
encrypt the credential.
:::

## First CLI decision

Choice returns a selected label, confidence, and the complete distribution:

```bash
pyjev choice "Where should this ticket go?" \
  --state "Stripe checkout fails" \
  --option billing="Payments and refunds" \
  --option engineering="Technical failures" \
  --option sales="Purchasing questions" \
  --json
```

`--json` is intended for programs and preserves all result metadata.

## First Python decision

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

## First named decision

Create `.pyjev.toml`:

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

Then run it from the project directory:

```bash
echo "Stripe webhooks fail" | pyjev decide ticket-route --json
```

Continue with [Named decisions](named-decisions.md), [Confidence](confidence.md),
[Python API](python-api.md), and [CLI](cli.md).
