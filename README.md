# pyjev

Reusable, confidence-aware [Jev](https://docs.typesafe.ai/introduction) decisions for Python and the shell.

`pyjev` is a thin convenience layer over TypeSafe's official `typesafe-sdk`. TypeSafe owns HTTP transport, retries, API semantics, and SDK models; pyjev adds reusable named decisions, credential ergonomics, output safety, and a small CLI.

## Install

```bash
pip install -e .
# development
pip install -e '.[dev]'
```

For a published release, install the package from PyPI or use `uv tool install pyjev`.

## Authentication

Credential lookup has this precedence:

1. explicit Python `api_key=...`;
2. `TYPESAFE_API_KEY`;
3. the operating-system keyring;
4. `~/.config/pyjev/credentials` (or `$XDG_CONFIG_HOME/pyjev/credentials`).

For local use, `pyjev auth set` first tries the operating-system keyring. If no usable
keyring backend is available, interactive use can fall back to
`~/.config/pyjev/credentials` after an explicit warning. The fallback is plaintext
and should be readable only by your user account. Restrictive file permissions do not
make it encrypted or equivalent to a keyring.

Use the environment variable in CI and ephemeral environments:

```bash
export TYPESAFE_API_KEY='...'
```

Local authentication commands:

```bash
pyjev auth set
pyjev auth status
pyjev auth delete
```

Storage can be selected explicitly:

```bash
pyjev auth set --storage keyring
pyjev auth set --storage file
```

`pyjev auth set --api-key SECRET` is retained for automation, but may expose the
secret in shell history. Use `--storage file` only when the plaintext tradeoff is
acceptable. API keys must never be stored in project `.pyjev.toml` decision files;
the optional plaintext fallback is a separate user-level credential file.

## CLI

### Primitive decisions

Noul evaluates a yes/no probability:

```bash
pyjev ask "Does this customer request a refund?" \
  --state "Please return my money."
```

Choice preserves the selected label, confidence, and full probability distribution:

```bash
pyjev choice "Where should this ticket go?" \
  --state "Stripe checkout fails" \
  --option billing="Payments and refunds" \
  --option engineering="Technical failures" \
  --option sales="Purchasing questions"
```

Score accepts 2–10 ordered levels:

```bash
pyjev score "How urgent is this?" \
  --state "Production is down" \
  --level "Can wait" \
  --level "Normal" \
  --level "Urgent" \
  --level "Critical"
```

State can come from `--state`, `--state-file`, or stdin. Add `--state-json` to decode it as JSON. Use `--json` for structured output or `--value` for only the selected value. These options cannot be combined.

### Confidence gates

Choice and Score support `--min-confidence`:

```bash
if TEAM="$(cat ticket.txt | pyjev choice "Route this ticket" \
  --option billing --option engineering --option sales \
  --min-confidence 0.85 --value)"; then
  route_to "$TEAM"
else
  case "$?" in
    3) human_review ;;
    *) echo "pyjev failed" >&2; exit 1 ;;
  esac
fi
```

The gate is evaluated before successful output. A failed `--value` gate emits an empty stdout and a concise stderr message. With `--json`, a failed gate emits an explicit envelope containing `gate.passed`, `minimum_confidence`, `confidence`, and the full `result`.

Noul has a probability of true rather than a Choice/Score confidence, so `--min-confidence` is not supported for Noul decisions.

### Exit codes

| Exit | Meaning                                                                                             |
| ---: | --------------------------------------------------------------------------------------------------- |
|    0 | Successful result and any confidence gate passed                                                    |
|    1 | Runtime failure: credentials, keyring, credential-file, TypeSafe API, network, or configuration I/O |
|    2 | CLI usage or local argument validation error                                                        |
|    3 | Valid Choice/Score result obtained, but confidence gate failed                                      |

Expected TypeSafe failures are concise and do not print tracebacks by default.

## Reusable named decisions

Create `.pyjev.toml` in a project:

```toml
[decision.ticket-route]
type = "choice"
question = "Which team should handle this support request?"
model = "jev-latest"

[decision.ticket-route.options]
billing = "Billing, invoice, payment, or refund issue"
engineering = "Technical problem or product bug"
sales = "Purchasing, pricing, or procurement question"
other = "None of the above"

[decision.urgency]
type = "score"
question = "How urgent is this?"
levels = ["can wait", "normal", "urgent", "critical"]

[decision.refund-request]
type = "noul"
question = "Does the customer request a refund?"
true = "The customer wants money returned."
false = "The customer does not request money returned."
```

Named decisions are read-only declarations. They support Noul, Choice, Score, and an optional per-decision model. Unknown fields and invalid cardinalities are rejected before any API request.

Configuration precedence is:

1. explicit Python `config=` or CLI `--config PATH`;
2. `PYJEV_CONFIG`;
3. the nearest `.pyjev.toml` in the current directory or a parent directory.

Use the management commands to inspect declarations:

```bash
pyjev decision list
pyjev decision list --json
pyjev decision show ticket-route --json
pyjev decision validate
```

Run a named decision from the shell:

```bash
echo "Stripe webhooks keep failing" |
  pyjev decide ticket-route --min-confidence 0.85 --json
```

The command supports the same state, model, config, output, and confidence options as primitive Choice/Score commands.

## Python API

```python
from pyjev import Jev

with Jev() as jev:
    result = jev.decide(
        "ticket-route",
        state="Stripe webhooks keep failing",
    )

if result.confidence >= 0.85:
    route(result.value)
```

A short-lived top-level convenience function is also available:

```python
from pyjev import decide

result = decide(
    "ticket-route",
    "Stripe checkout fails",
    config="ops/.pyjev.toml",
    model="jev-latest",  # explicit override wins over the TOML model
)
```

Direct primitive methods remain available:

```python
from pyjev import Jev

with Jev() as jev:
    choice = jev.choice(
        "Which team should handle this?",
        state="Stripe checkout crashes.",
        choices={
            "billing": "Payments and refunds",
            "engineering": "Technical failures",
            "sales": "Purchasing questions",
        },
    )
    score = jev.score(
        "How urgent is this?",
        state="Production is down.",
        levels=["Can wait", "Normal", "Urgent", "Critical"],
    )
```

`ChoiceResult` and `ScoreResult` preserve `value`, `confidence`, all probabilities, model, usage, raw answer data, and `request_id`. `NoulResult.value` is the raw probability of true and is not converted to a boolean.

For several heterogeneous questions, use `jev.run(...)` to send one mixed request through the SDK.

## Connect Four tactical-proof example

`examples/connect_four.py` keeps exact Connect Four mechanics and short bounded tactical proofs in Python. In addition to immediate wins and blocks, it checks whether an opponent reply creates a fork with no legal tactical escape. Proven losing candidates are removed before Jev is called.

This is deliberately **not** a general Connect Four search engine: Python does not assign positional scores or run minimax for strategic evaluation. When multiple tactically admissible moves remain, Jev still makes the strategic judgment. The observed bad move was an action-space problem, not merely low confidence: a model cannot avoid a proven loss if the application offers it as a choice.

Run the playable demo with a configured API key:

```bash
python examples/connect_four.py
python examples/connect_four.py --strategy aggressive
python examples/connect_four.py --debug
python examples/connect_four.py --debug --trace connect-four.jsonl
```

`--debug` prints deterministic board facts, candidate keep/reject explanations, forcing proof branches, and the exact structured request and Jev response metadata for real calls. `--trace PATH` appends one JSONL record per completed turn; records contain no API credentials. `--self-play` runs the same player-relative tactical filter for Jev-X versus Jev-O.

## Versioning and development
Versions are derived from Git tags with `setuptools-scm`; a tagged `v0.1.0` checkout builds as `0.1.0`.

```bash
python -m compileall pyjev
pytest
ruff check .
python -m build
twine check dist/*
```

No live API key is required for the unit tests. CI tests Python 3.10–3.14, builds wheel and sdist artifacts, checks package metadata, and smoke-tests an installed wheel.

## License

Apache-2.0.
