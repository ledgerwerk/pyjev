[![PyPI - Version](https://img.shields.io/pypi/v/pyjev)](https://pypi.org/project/pyjev/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pyjev)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pyjev)
[![codecov](https://codecov.io/gh/ledgerwerk/pyjev/graph/badge.svg?token=34W6LDpSJB)](https://codecov.io/gh/ledgerwerk/pyjev)

# pyjev

**Turn Jev judgments into reusable, inspectable decision contracts for Python, shell, and CI.**

`pyjev` is a decision-engineering layer over TypeSafe's official `typesafe-sdk`.
The SDK is the right tool for making System One requests. pyjev is for the point
where a judgment becomes part of your application: give it a stable name, validate
and inspect it offline, reuse it from Python and shell, preserve its uncertainty,
and apply explicit local policy before your code acts.

pyjev does not replace TypeSafe's transport or model APIs. It delegates requests,
retries, assets, authentication, and API errors to `typesafe-sdk`, then adds
source-controlled decision contracts, deterministic request compilation,
application-level result and policy primitives, reusable semantic recipes, and
bounded automation tooling.

## SDK or pyjev?

| Need                                                          | `typesafe-sdk`                         | `pyjev`                                                  |
| ------------------------------------------------------------- | -------------------------------------- | -------------------------------------------------------- |
| Make a System One request                                     | Yes, the primary API                   | Yes, delegates to the SDK                                |
| Sync and async clients                                        | Yes                                    | Yes, with pyjev decision and recipe APIs                 |
| Typed SDK questions and answers                               | Yes                                    | Wraps SDK results in pyjev result and workflow contracts |
| Low-level retry, transport, and request controls              | Yes                                    | Intentionally delegated to the SDK                       |
| Named project decisions                                       | Build your own application abstraction | Declare them in `.pyjev.toml`                            |
| Validate or inspect a decision without credentials or network | Build your own tooling                 | `decision validate` and `decision compile`               |
| Deterministic decision-spec fingerprint                       | Build your own                         | Included in compiled decision output                     |
| Reuse one named decision from Python and shell/CI             | Build your own                         | Yes                                                      |
| Shell-safe confidence gate and exit contract                  | Build your own                         | Yes                                                      |
| Inspectable `build -> execute -> interpret` recipes           | Cookbook or application code           | Yes                                                      |
| Bounded, ordered async batch records                          | Build your own                         | `pyjev.amap`                                             |
| Latest or lower-level SDK features                            | Yes                                    | Use the SDK directly when pyjev does not expose them     |

> **Rule of thumb:** If a call is a local implementation detail, the SDK is
> usually enough. If the judgment has a stable name, is reviewed or reused, crosses
> Python and shell/CI boundaries, or needs explicit interpretation and policy,
> pyjev starts to pay for itself.

## A 60-second decision contract

Declare a recurring judgment in version-controlled `.pyjev.toml`:

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

Validate the project contract and inspect the normalized request and fingerprint
without credentials or a network call:

```bash
pyjev decision validate
pyjev decision compile ticket-route --state "Stripe checkout fails"
```

Execute the same named contract from shell:

```bash
printf '%s\n' "Stripe checkout fails" | pyjev decide ticket-route --json
```

Or execute it from Python:

```python
from pyjev import Jev

with Jev() as jev:
    result = jev.decide("ticket-route", state="Stripe checkout fails")

print(result.value, result.confidence, result.probabilities)
```

The useful abstraction is not `jev.decide()` versus `client.system_one()`. It is
that `ticket-route` is now a project-level contract that can be validated and
inspected independently, then invoked consistently from multiple surfaces.

## Why contracts instead of inline SDK calls?

A named decision can be:

- identified and reused by a stable project-level name;
- reviewed and changed in source control;
- validated locally before credentials or network access are involved;
- compiled into a normalized request preview with a deterministic spec fingerprint;
- tested separately from transport and runtime state;
- used by Python code, shell scripts, and CI;
- interpreted through explicit caller-owned policy.

A fingerprint helps distinguish a decision-spec change from runtime state and can
support snapshots or review evidence. It is not tamper-proofing or a persisted
audit record. See [Why pyjev?](docs/why-pyjev.md) for the product boundary and a
side-by-side example.

## From primitives to application workflows

TypeSafe provides the underlying Jev primitives. pyjev also packages recurring
application patterns as inspectable recipes:

- `find`: rank candidates and independently judge whether any actually applies;
- `extract`: discover literal candidates deterministically, then disambiguate only
  among those candidates or `none`;
- `verify`: distinguish support, contradiction, and no evidence;
- `classify`: support closed-set or independent multi-label judgments;
- `match`: return categorical `same`, `unclear`, or `different` outcomes;
- `route`: produce a typed proposal without invoking application handlers;
- `rerank`: make independent relevance judgments;
- `screen`: provide an advisory semantic prefilter, not a security boundary.

Recipes separate deterministic `build`, Jev-backed `execute`, and deterministic
`interpret` stages. This lets applications inspect request plans and test
interpretation without mixing them with transport. For example, `extract` can use
Python to find literal invoice IDs, ask Jev to choose among only those literals,
then let caller-owned policy decide whether to normalize, review, or persist the
result. See [Semantic recipes](docs/recipes.md).

## Primitive results

- **Noul:** probability of true.
- **Choice:** selected label, probabilities, and confidence.
- **Score:** expected score over ordered levels, probabilities, and confidence.
- **Box:** one set of normalized image coordinates and nullable confidence. Box and image input are experimental upstream and require explicit opt-in.

## Application policy

Python result pipelines apply caller-owned policy to an already returned result.
They do not hide the network call or execute side effects:

```python
from pyjev.pipeline import require_confidence

outcome = result | require_confidence(0.70)
if outcome.passed:
    route_to(outcome.value)
else:
    human_review(outcome.result)
```

The CLI can apply the same kind of explicit confidence gate. A valid Choice or
Score below the requested threshold exits with code `3` and emits no actionable
`--value`. Confidence is a Jev signal, not a guarantee of correctness, and
thresholds belong to the caller. A gate rejection is distinct from request or
transport failure.

## Structured questions

Jev instructions and criteria do not have to be prose strings. pyjev preserves objects and arrays as structured question content in direct Python calls, named `.pyjev.toml` contracts, offline compilation, and fingerprints. Structure is useful when it makes fields and relationships clearer, not as ceremony for a one-line question. See [Structured question content](docs/structured-content.md).

```toml
[decision.ticket-route]
type = "choice"
question = { task = "Route the ticket", fields = ["subject", "body"] }

[decision.ticket-route.options.billing]
covers = ["invoice", "charge", "refund"]

[decision.ticket-route.options.engineering]
covers = ["bug", "technical failure"]
```

## Box localization (experimental)

Box always returns one set of normalized image coordinates for one target. Image input and Box are experimental upstream and require explicit opt-in. The official SDK owns image assets and transport:

```python
from pathlib import Path
from pyjev import Image, Jev

with Jev(images=True) as jev:
    location = jev.box(
        {"target": "coffee mug", "image": "photo"},
        state={"photo": Image(Path("kitchen.jpg"))},
    )

print(location.box)
print(location.confidence)
```

A Box result has no explicit not-found outcome. When absence matters, ask a companion Noul question in the same bundle. pyjev's CLI can inspect and compile Box decisions offline, but cannot upload images or execute them live. See [Image inputs](docs/images.md) for normalized coordinates, presence checks, and limitations.

## When a named contract is not the right abstraction

Not every judgment belongs in `.pyjev.toml`. If options or rubrics are computed
dynamically from deterministic application state, use `Jev.choice`, `Jev.noul`,
`Jev.score`, or the corresponding CLI commands directly. Keep deterministic
constraints in ordinary code and use Jev for judgment among the remaining valid
alternatives.

If you only need a few inline System One calls, have no need for pyjev's result,
policy, credential, or CLI conventions, or need custom SDK transport/retry controls,
custom response models, or a lower-level feature not represented by pyjev,
calling `typesafe-sdk` directly may be simpler. The official client remains available
through `jev.client`, and callers can inject their own SDK client.

## Batch and automation

`pyjev.amap` adds bounded concurrency, stable input/output order, row-level result
records, optional IDs and metadata, fail-fast scheduling semantics, cancellation
propagation, and token-usage aggregation for independent async calls. It adds no
hidden retries beyond SDK behavior. JSON, JSONL, Markdown, and deterministic
`pluck` output support shell and CI workflows. These are application conventions
around SDK calls, not replacements for SDK transport or async primitives.

## Image inputs (experimental)

TypeSafe currently labels image inputs dreamer-ready and requires explicit opt-in.
pyjev forwards the official SDK `Image` object and leaves asset serialization and
upload to `typesafe-sdk`:

```python
from pathlib import Path

from pyjev import Image, Jev

with Jev(images=True) as jev:
    result = jev.noul(
        "Is a person visible in `photo`?",
        state={"photo": Image(Path("door-camera.jpg"))},
    )
```

Images can be placed in state and structured questions. Pass named references
with `assets={"<reference>": Image(...)}`. See [Image inputs](docs/images.md) for
limits, examples, and experimental-status details.

## Authentication

Use the hidden interactive prompt for local setup or `TYPESAFE_API_KEY` in CI:

```bash
pyjev auth set
pyjev auth test
export TYPESAFE_API_KEY='...'
```

`pyjev auth test` performs one minimal official-SDK request and reports safe
credential-source and model metadata. Do not put secrets in `.pyjev.toml`. The
explicit `auth set --api-key` option remains available for compatibility but is
unsafe because shell history and process inspection may expose it.

## pyjev, the SDK, and other tools

- Use `typesafe-sdk` directly for isolated calls, low-level TypeSafe controls, or
  primitives pyjev does not expose.
- Use `pyjev` when decisions need stable identity, offline inspection, reusable
  recipes, explicit local policy, or consistent behavior across Python and
  automation.
- Use a standalone provider-aware CLI/MCP tool such as `jev-cli` for its direct
  shell, provider, MCP, and agent-skill workflows.

These tools operate at different layers. See [the comparison](docs/comparisons.md)
for the dated feature matrix.

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

- [Why pyjev?](docs/why-pyjev.md)
- [Full documentation](docs/index.md)
- [Getting started](docs/getting-started.md)
- [Named decisions](docs/named-decisions.md)
- [Structured question content](docs/structured-content.md)
- [Semantic recipes](docs/recipes.md)
- [Python API](docs/python-api.md)
- [Image inputs](docs/images.md)
- [CLI and exit codes](docs/cli.md)
- [Agent skill](docs/agent-skill.md)
- [Runnable examples](examples/README.md)
- [TypeSafe Jev documentation](https://docs.typesafe.ai/)

## License

Apache-2.0
