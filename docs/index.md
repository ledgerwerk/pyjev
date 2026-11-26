# pyjev

**Reusable, inspectable Jev decision contracts for Python applications and automation.**
`typesafe-sdk` is the execution layer for TypeSafe System One requests. `pyjev` is for decisions that become part of an application's operating contract: named declarations, offline inspection, reusable interpretation and policy, semantic recipes, and consistent Python/shell/CI behavior.

If you only need a few inline Jev calls, start with `typesafe-sdk`. Use pyjev when the judgment itself needs to be named, reviewed, reused, tested, or safely automated.

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
why-pyjev
concepts
structured-content
recipes
python-api
images
cli
named-decisions
patterns
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
- [Why pyjev?](why-pyjev.md)
- [Named decisions](named-decisions.md)
- [Decision patterns](patterns.md)
- [Python API](python-api.md)
- [Image inputs](images.md)
- [Structured question content](structured-content.md)
- [Semantic recipes](recipes.md)
- [CLI and exit codes](cli.md)
- [Confidence policy](confidence.md)
- [Authentication](authentication.md)
- [Agent skill](agent-skill.md)
- [pyjev vs jev-cli](comparisons.md)
- [Runnable examples](examples.md)
