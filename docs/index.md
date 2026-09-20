# pyjev

**Reusable, inspectable Jev decision contracts for Python applications and automation.**

`pyjev` is the Python application layer above TypeSafe's official
`typesafe-sdk`. It adds typed synchronous and native asynchronous clients,
version-controlled `.pyjev.toml` decision contracts, offline validation and
compilation, uncertainty-preserving results, credential ergonomics, and
confidence-aware application policy.

## Why pyjev?

- Embed Jev in Python applications with dependency injection and typed results.
- Declare stable named decisions and bundles once, then reuse them from Python,
  shell, CI, or an agent workflow.
- Inspect and compile requests without credentials, client construction, or
  network access.
- Preserve probabilities, confidence, usage, request IDs, and raw metadata.
- Gate automation explicitly without consuming a low-confidence value by mistake.
- Let the official SDK own transport, retries, API models, authentication, and
  API error semantics.

## 60-second workflow

```bash
cat > .pyjev.toml <<'EOF'
[pyjev]
schema = 1

[decision.ticket-route]
type = "choice"
question = "Which team should handle this support request?"

[decision.ticket-route.options]
billing = "Billing or refunds"
engineering = "Technical problem or product bug"
sales = "Purchasing or procurement"
EOF

pyjev decision validate
pyjev decision compile ticket-route --state "Stripe checkout fails"
echo "Stripe checkout fails" | pyjev decide ticket-route --json
```

The same contract is available to Python callers:

```python
from pyjev import Jev

with Jev() as jev:
    result = jev.decide("ticket-route", state="Stripe checkout fails")

print(result.value, result.confidence, result.probabilities)
```

## Direct dynamic decisions

For criteria that depend on runtime deterministic logic, use `Jev`/`AsyncJev`
or the direct `pyjev choice`, `pyjev noul`, and `pyjev score` commands. The CLI
is a useful shell and CI interface to pyjev's application layer, not its only
abstraction.

## Documentation

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
agent-skill
debugging
examples
comparisons
api/index
development
changelog
```

- [Getting started](getting-started.md)
- [Named decisions](named-decisions.md)
- [Python API](python-api.md)
- [CLI and exit codes](cli.md)
- [Confidence policy](confidence.md)
- [Authentication](authentication.md)
- [Agent skill](agent-skill.md)
- [pyjev vs jev-cli](comparisons.md)
- [Runnable examples](examples.md)
