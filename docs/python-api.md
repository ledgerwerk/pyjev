# Python API

## Creating a client

```python
from pyjev import Jev

with Jev(model="jev-latest") as jev:
    result = jev.choice("Route this ticket", state=ticket, choices=choices)
```

`Jev` delegates transport, retries, API semantics, and models to `typesafe-sdk`.
The context manager closes clients created by `Jev`.

## Primitive operations

- `jev.noul(...)` and its `jev.ask(...)` alias return `NoulResult`.
- `jev.choice(...)` accepts a mapping of labels to criteria or a sequence of labels.
- `jev.score(...)` accepts 2–10 ordered levels.

All validation happens before the SDK call. Results preserve uncertainty instead of
collapsing to a scalar convenience value.

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

`Jev.evaluate()` and `AsyncJev.evaluate()` accept `NoulDecision`, `ChoiceDecision`, `ScoreDecision`, and `BundleDecision`. Explicit `model=` overrides the declaration's model; otherwise the declaration model is used. A bundle shares one request and returns the usual typed child results in a `BundleResult`. Child model overrides are not allowed, matching named bundle rules. Constructing and locally validating decisions does not resolve credentials or make a request. `decide()` remains the convenient interface for declarations stored in `.pyjev.toml`.

## Named decisions

```python
result = jev.decide("ticket-route", state=ticket, config="ops/.pyjev.toml")
```

Explicit call model overrides the decision model. Configuration discovery and schema
rules are described in [Named decisions](named-decisions.md).

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

## Result objects

Use `.value`, `.confidence`, `.probabilities`, and `.legend` as applicable. Every result
also preserves model, usage, raw answer data, and request ID. `NoulResult.value` remains
the raw probability of true.

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

`answer(name)` selects the exact typed child from a `BundleResult`. Confidence gates accept only `ChoiceResult` and `ScoreResult`, and preserve the complete result in either an `Accepted` or `Rejected` outcome. A rejected outcome has no `.value` attribute, so a below-threshold result cannot be mistaken for permission to act.

For `NoulResult`, use the separate probability policy:

```python
from pyjev.pipeline import require_probability

outcome = result | require_probability(at_least=0.80)
```

Thresholds are inclusive and must be finite values from 0 through 1. Choice and Score confidence is a Jev-supplied signal, not the probability that an answer is correct. The same local pipeline works after either synchronous or asynchronous evaluation.

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
