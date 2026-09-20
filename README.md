# pyjev

Reusable, confidence-aware [Jev](https://docs.typesafe.ai/introduction) decisions for Python and the shell.

`pyjev` is intentionally a thin convenience layer over TypeSafe's official `typesafe-sdk`. It does not reimplement the HTTP API.

## MVP features

- flat package layout (`pyjev/`, no `src/` directory)
- dynamic versions from Git tags via `setuptools-scm`
- Python API for Noul, Choice, Score, and mixed-question requests
- `pyjev` CLI with stdin/file support and JSON output
- API-key lookup from `TYPESAFE_API_KEY` or the OS keyring
- confidence gating for Choice and Score (`--min-confidence` exits with code 2)

## Install

```bash
pip install -e .
# or
uv pip install -e .
```

For a CLI-only install from a future PyPI release:

```bash
uv tool install pyjev
```

## Authentication

Environment variables are preferred in CI:

```bash
export TYPESAFE_API_KEY='...'
```

For local use, store the key in the operating-system keyring:

```bash
pyjev auth set
pyjev auth status
```

If no usable keyring backend is available, use `TYPESAFE_API_KEY` instead.

## CLI

Noul / yes-no probability:

```bash
pyjev ask "Does this customer request a refund?" \
  --state "I want my money back"
```

Choice:

```bash
pyjev choice "Where should this ticket go?" \
  --state "Stripe checkout fails" \
  --option billing="Payments and refunds" \
  --option engineering="Technical failures" \
  --option sales="Purchasing questions"
```

Machine-friendly output:

```bash
cat ticket.txt | pyjev choice "Where should this ticket go?" \
  --option billing \
  --option engineering \
  --option sales \
  --json
```

Only print the selected value:

```bash
TEAM=$(cat ticket.txt | pyjev choice "Route this ticket" \
  --option billing --option engineering --option sales --value)
```

Confidence gate (exit status `2` if confidence is below the threshold):

```bash
pyjev choice "Route this ticket" \
  --state "Something odd happened" \
  --option billing --option engineering --option sales \
  --min-confidence 0.85
```

Score:

```bash
pyjev score "How urgent is this?" \
  --state "Production is down for all customers" \
  --level "Can wait" \
  --level "Normal" \
  --level "Urgent" \
  --level "Critical"
```

Structured state can be JSON-decoded:

```bash
pyjev ask "Is this order high value?" \
  --state '{"total": 5000, "currency": "EUR"}' \
  --state-json
```

Mixed questions in one request:

```json
{
  "state": "I was charged twice and I am furious.",
  "questions": {
    "billing": {
      "type": "noul",
      "instructions": "Is this about billing?"
    },
    "tone": {
      "type": "choice",
      "instructions": "What is the tone?",
      "criteria": {
        "calm": null,
        "angry": null
      }
    }
  }
}
```

```bash
pyjev run request.json
# or
cat request.json | pyjev run -
```

List models available to the account:

```bash
pyjev models
```

## Python

```python
from pyjev import Jev

with Jev() as jev:
    result = jev.choice(
        "Which team should handle this?",
        state="Stripe checkout crashes.",
        choices={
            "billing": "Payments and refunds",
            "engineering": "Technical failures",
            "sales": "Purchasing questions",
        },
    )

print(result.value)
print(result.confidence)
print(result.probabilities)
```

Noul:

```python
with Jev() as jev:
    result = jev.ask(
        "Does this customer request a refund?",
        state="Please return my money.",
    )

print(result.value)  # 0..1 probability of yes/true
```

Score:

```python
with Jev() as jev:
    result = jev.score(
        "How urgent is this?",
        state="Production is down.",
        levels=["Can wait", "Normal", "Urgent", "Critical"],
    )

print(result.value)       # expected score, potentially fractional
print(result.confidence)
```

For several independent questions, use one API request:

```python
from typesafe_sdk import Choice, Noul
from pyjev import Jev

with Jev() as jev:
    response = jev.run(
        state="I was charged twice and I am furious.",
        questions={
            "billing": Noul(instructions="Is this about billing?"),
            "tone": Choice(
                instructions="What is the tone?",
                criteria={"calm": None, "angry": None},
            ),
        },
    )
```

## Dynamic versioning

There is no hard-coded package version in `pyproject.toml`.

`setuptools-scm` derives versions from Git tags. Use tags such as:

```bash
git tag v0.1.0
python -m build
```

A normal tagged checkout builds as `0.1.0`. Commits after a tag receive an SCM-derived development version. The source snapshot also supports extracting from a directory named `pyjev-X.Y.Z`; otherwise a non-Git snapshot falls back to `0.0.0` so it remains buildable.

At runtime:

```python
import pyjev
print(pyjev.__version__)
```

## Development

```bash
pip install -e '.[dev]'
pytest
ruff check .
```

No live API key is required for the unit tests.

## License

Apache-2.0.
