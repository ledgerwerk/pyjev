# Python API

## Creating a client

```python
from pyjev import Jev

with Jev(model="jev-latest") as jev:
    result = jev.choice("Route this ticket", state=ticket, choices=choices)
```

`Jev` delegates transport, retries, API semantics, and models to `typesafe-sdk`.
The context manager closes clients created by `Jev`.

`Jev` is not intended to hide `typesafe-sdk`. For a one-off low-level request, the SDK may be the simpler API. `Jev` becomes useful when you want named decisions, stable result wrappers, recipes, policy stages, or cross-surface conventions. The underlying SDK client remains available as `jev.client`. See [Why pyjev?](why-pyjev.md).

## Primitive operations

- `jev.noul(...)` and its `jev.ask(...)` alias return `NoulResult`.
- `jev.choice(...)` accepts a mapping of labels to criteria or a sequence of labels.
- `jev.score(...)` accepts 2–10 ordered levels.

- `Jev.box(...)` and native `AsyncJev.box(...)` return `BoxResult` with normalized coordinates and nullable confidence. Box requests require explicit image opt-in.

All validation happens before the SDK call. Results preserve uncertainty instead of
collapsing to a scalar convenience value.

## Content types

Public annotations reuse the official SDK aliases. `Content` represents text, JSON-like objects and arrays, and SDK assets such as `Image`; `JSONContent` is the corresponding asset-free JSON form. `ContentValue` and `JSONValue` describe nested values. pyjev re-exports these aliases instead of defining a competing recursive type. See [Structured question content](structured-content.md) for supported fields and named TOML examples.

## In-memory decisions

The same typed decision declarations used by named contracts can be assembled at runtime. They are public constructors and can be evaluated without writing a `.pyjev.toml` file:

```python
from pyjev import BundleDecision, ChoiceDecision, Jev, NoulDecision

decision = BundleDecision(
    name="ticket-triage",
    questions={
        "route": ChoiceDecision("route", "Which team?", {"billing": None, "engineering": None}),
        "refund": NoulDecision("refund", "Is a refund requested?"),
    },
)

with Jev(model="jev-latest") as jev:
    result = jev.evaluate(decision, state={"message": "Checkout failed; please refund me."})
```

`Jev.evaluate()` and `AsyncJev.evaluate()` accept `NoulDecision`, `ChoiceDecision`, `ScoreDecision`, `BoxDecision`, and `BundleDecision`. Explicit `model=` overrides the declaration's model; otherwise the declaration model is used. A bundle shares one request and returns the usual typed child results in a `BundleResult`. Child model overrides are not allowed, matching named bundle rules. Constructing and locally validating decisions does not resolve credentials or make a request. `decide()` remains the convenient interface for declarations stored in `.pyjev.toml`.

## Named decisions

```python
result = jev.decide("ticket-route", state=ticket, config="ops/.pyjev.toml")
```

Explicit call model overrides the decision model. Configuration discovery and schema
rules are described in [Named decisions](named-decisions.md).

## Image inputs (experimental)

pyjev re-exports the official SDK `Image` class. Image support requires `typesafe-sdk>=0.7.6` and explicit `images=True`; TypeSafe currently describes it as dreamer-ready and experimental. When enabled, pyjev sends the required image opt-in header on every System One request. Inline `Image` objects in state, instructions, and criteria are passed to the SDK unchanged.

```python
from pathlib import Path

from pyjev import Image, Jev

with Jev(images=True) as jev:
    result = jev.choice(
        "Which product matches <reference>?",
        state={"candidate": Image(Path("candidate.jpg"))},
        choices={"same": None, "different": None},
        assets={"<reference>": Image(Path("reference.jpg"))},
    )
```

`assets=` is available on `ask`, `noul`, `choice`, `score`, `evaluate`, `decide`, and `run`. `AsyncJev(images=True)` exposes the same behavior with native async calls and `await`. The flag also works with an injected SDK client; pyjev does not reconstruct or take ownership of that client.

For advanced SDK operations such as `attach_assets`, use `jev.client`. Direct structured image placement and `assets=` are the preferred pyjev interfaces. Image support is experimental, and requests send the supplied image data to the configured API. See [Image inputs](images.md) for limits, preparation, errors, and policy considerations.

## Mixed questions

`jev.run(state=..., questions=...)` sends several SDK question objects in one request.
Named bundles provide the same pattern from `.pyjev.toml` and return `BundleResult`.

## Compiling offline

```python
from pyjev import compile_decision

compiled = compile_decision("ticket-route", state="Stripe checkout fails")
print(compiled.to_dict())
```

Compilation resolves and validates configuration without creating a client or reading
credentials. It is useful for review, debugging, and agent tooling.

`CompiledDecision.fingerprint` is a deterministic SHA-256 identifier for the
validated declaration. It excludes the runtime state passed to
`compile_decision()` and does not include credentials or absolute config paths.
The serialized preview includes `schema = 1`, a reproducible config identifier,
the fingerprint, and the normalized official SDK request shape.

## Injected clients

```python
from typesafe_sdk import TypeSafeClient
from pyjev import Jev

client = TypeSafeClient(...)
jev = Jev(client=client)
# use jev
jev.close()  # does not close caller-owned client
```

An injected client is caller-owned. Constructor options such as `api_key`, `model`, and
`timeout` cannot be combined with it.

## Dropping down to the SDK

Use `jev.client` for SDK operations outside pyjev's higher-level surface, or inject your own SDK client when you need to control its construction and lifecycle. This preserves the SDK as the low-level request and transport boundary; pyjev does not mirror every SDK option. See [TypeSafe SDK comparisons](comparisons.md#pyjev-and-typesafe-sdk).

## Result objects

Use `.value`, `.confidence`, `.probabilities`, and `.legend` as applicable. Every result
also preserves model, usage, raw answer data, and request ID. `NoulResult.value` remains
the raw probability of true.
`BoxResult.value` and `.box` expose normalized edge coordinates; its confidence may be `None`.

## Result pipelines

The optional `pyjev.pipeline` module composes already returned result objects with local policy stages. The pipe never creates a client or performs network I/O, so the Jev call remains visible:

```python
from pyjev import Jev
from pyjev.pipeline import answer, require_confidence

policy = answer("intent") | require_confidence(0.70)

with Jev() as jev:
    result = jev.decide("support-triage", state={"message": message})

outcome = result | policy
if outcome.passed:
    route_to(outcome.value)
else:
    human_review(outcome.result)
```

`answer(name)` selects the exact typed child from a `BundleResult`. Confidence gates accept `ChoiceResult`, `ScoreResult`, and `BoxResult`, and preserve the complete result in either an `Accepted` or `Rejected` outcome. A rejected outcome has no `.value` attribute, so a below-threshold result cannot be mistaken for permission to act.

For `NoulResult`, use the separate probability policy:

```python
from pyjev.pipeline import require_probability

outcome = result | require_probability(at_least=0.80)
```

Thresholds are inclusive and must be finite values from 0 through 1. Choice, Score, and Box confidence is a Jev-supplied signal, not the probability that an answer is correct. Box confidence is distinct from its coordinates and may be `None`; a minimum-confidence gate rejects a missing value. The same local pipeline works after either synchronous or asynchronous evaluation.

## Async API

When the installed official SDK supports native async transport, `AsyncJev` exposes the
same primitive, named-decision, bundle, validation, model-precedence, and result semantics:

```python
from pyjev import AsyncJev

async with AsyncJev() as jev:
    result = await jev.choice("Route this ticket", state=ticket, choices=choices)
```

It uses `AsyncTypeSafeClient` directly and does not hide synchronous work in a thread pool.

## Bounded async batches

Use `amap` for independent states that can be evaluated concurrently. It preserves input order, returns one `BatchRecord` per input, and aggregates token usage from successful typed results:

```python
from pyjev import AsyncJev, amap

async with AsyncJev() as jev:
    batch = await amap(
        tickets,
        lambda ticket: jev.decide("ticket-triage", state=ticket.state),
        concurrency=4,
        ids=[ticket.id for ticket in tickets],
    )

for row in batch.records:
    if row.ok:
        consume(row.id, row.result)
    else:
        log_failure(row.id, row.error.kind)

print(batch.summary.to_dict())
```

Failures are row-local by default. `fail_fast=True` stops scheduling after the first observed failure, waits for already-running workers, and marks the remaining rows `not_started`. Worker exception text is deliberately omitted from `BatchError` because it may contain secrets or user data. Cancellation cancels workers and propagates rather than returning a partial result. The batch layer adds no retries; SDK behavior is unchanged. A policy rejection inside a successful result is still an execution success, not a batch error.
