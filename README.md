[![PyPI - Version](https://img.shields.io/pypi/v/pyjev)](https://pypi.org/project/pyjev/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pyjev)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pyjev)
[![codecov](https://codecov.io/gh/ledgerwerk/pyjev/graph/badge.svg?token=34W6LDpSJB)](https://codecov.io/gh/ledgerwerk/pyjev)

# pyjev

**Confidence-aware Jev decisions for Python, shell, CI, and automation.**

`pyjev` is a thin operational layer over TypeSafe's official `typesafe-sdk`. It
preserves Jev probabilities, confidence, and response metadata while adding
reusable named decisions, shell-safe output, credential ergonomics, local
validation, request inspection, and confidence gates.

## Install

```bash
pip install pyjev
# or: uv tool install pyjev
```

For a development checkout:

```bash
pip install -e '.[dev,docs]'
```

## A first decision

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

## What pyjev adds

- direct Noul, Choice, and Score operations with uncertainty preserved;
- reusable `.pyjev.toml` decisions and mixed-question bundles;
- offline validation and request compilation;
- confidence-gated shell automation and stable exit codes;
- keyring, environment, and explicit plaintext-file credential support;
- request IDs, usage, raw metadata, and structured JSON for debugging.

The official `typesafe-sdk` remains responsible for transport, retries, API
models, authentication at the HTTP layer, and API error semantics. pyjev does
not invent probabilities or confidence calculations.

## Learn more

- [Full documentation](docs/index.md)
- [Runnable examples](examples/README.md)
- [TypeSafe Jev documentation](https://docs.typesafe.ai/)
- [Issues](https://github.com/ledgerwerk/pyjev/issues)

## License

Apache-2.0
