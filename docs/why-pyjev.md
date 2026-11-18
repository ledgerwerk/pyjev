# Why pyjev?

The official `typesafe-sdk` is the right tool for making TypeSafe System One
requests. `pyjev` is useful when a judgment should become a reusable part of an
application rather than remain an inline request.

> **The SDK executes System One requests. pyjev turns recurring Jev judgments
> into inspectable, reusable decision contracts and application workflows.**

`pyjev` is a decision-engineering layer over the official Python SDK. It keeps the
SDK as the transport and model boundary, while adding source-controlled decision
contracts, offline inspection and fingerprints, reusable policy gates, semantic
recipes, batch/output tooling, and a consistent contract across Python, shell,
CI, and agent workflows.

## The SDK is the execution layer

TypeSafe and Jev provide the model semantics and API. `typesafe-sdk` provides the
Python request and response models, synchronous and asynchronous clients,
transport, retries, authentication, assets, and API errors. Those are SDK
responsibilities, not pyjev's differentiators.

```text
TypeSafe / Jev
  model semantics and API

  typesafe-sdk
    request/response models, clients, transport, retries, assets,
    authentication, and API errors

    pyjev
      declaration -> validation -> inspection -> execution
                   -> interpretation -> caller policy

  application
    effects and business decisions
```

A raw SDK call is often the simplest answer to “make this System One request.”
The SDK remains the baseline and the low-level escape hatch. pyjev delegates
execution to it rather than creating a second transport stack.

## pyjev is the decision-contract layer

A recurring judgment can have a stable identity in `.pyjev.toml`. The contract
can then be validated, compiled, reviewed, executed, and interpreted consistently
by different parts of an application and its automation.

```text
declare       .pyjev.toml
validate      pyjev decision validate
inspect       pyjev decision compile <name> --state ...
review        source control + deterministic specification fingerprint
execute       Jev.decide(...) | AsyncJev.decide(...) | pyjev decide ...
interpret     typed result | local pipeline | CLI output/gate
```

For example, a `ticket-route` decision can be used from application code and
shell/CI without duplicating its Choice criteria:

```toml
[decision.ticket-route]
type = "choice"
question = "Which team should handle this support request?"

[decision.ticket-route.options]
billing = "Billing or refunds"
engineering = "Technical problem or product bug"
sales = "Purchasing or procurement"
```

```python
from pyjev import Jev

with Jev() as jev:
    result = jev.decide("ticket-route", state=ticket)
```

```bash
printf '%s' "$ticket" | pyjev decide ticket-route --json
```

The value is not shorter syntax for an SDK request. The judgment now has a
version-controlled project identity that can be inspected and reused.

## What changes when a judgment becomes application infrastructure

### Give it a stable identity

Named Noul, Choice, Score, and bundle decisions live in `.pyjev.toml`. A stable
name makes the declaration reusable and reviewable instead of repeating its
criteria in each call site.

### Inspect it without credentials

`pyjev decision validate` and `compile_decision()` validate declarations and
produce a normalized request preview without constructing a client, reading
credentials, or contacting the API. The compiled representation includes a
stable fingerprint for the validated decision specification. It can support
review, snapshots, distinguishing specification changes from runtime state, and
machine-readable code-review or deployment checks. It is not tamper-proofing or a
persisted audit log.

### Reuse it across Python and automation

A named contract can be run through `Jev` or `AsyncJev`, or invoked from the CLI
in shell and CI. That gives the application one declaration and consistent
pyjev-level result and gate conventions across runtime surfaces.

### Preserve uncertainty

pyjev result wrappers retain applicable values, confidence or probability
distributions, usage, model, raw response data, and request ID. They provide a
stable pyjev-facing result contract across decisions, recipes, pipelines, CLI
serialization, and batch tooling. The underlying SDK remains responsible for its
own typed request and response models. Confidence and probabilities are signals,
not guarantees of correctness.

### Separate judgment from policy

Python pipelines apply thresholds to an already returned result. CLI confidence
gates provide an automation contract: a valid low-confidence Choice or Score can
exit with code `3` without emitting an actionable `--value`. Thresholds and
follow-up actions belong to the caller. A rejected policy gate is not an API
failure, and the pipeline does not execute side effects.

### Package common semantic workflows

Recipes package deterministic planning, Jev execution through the caller's
client, and deterministic interpretation. For example, `extract` finds literal
candidates in Python, asks Jev to select only among those candidates or `none`,
then preserves evidence for deterministic normalization and caller-owned review
policy. `find` separates candidate ranking from applicability. `verify`
distinguishes support, contradiction, and no evidence. `route` returns a typed
proposal and never invokes handlers.

The `build -> execute -> interpret` split makes request shape, call count, policy
inputs, and result interpretation easier to inspect and test separately from the
network call. See [Semantic recipes](recipes.md).

## A side-by-side example

A direct SDK call is appropriate when the route is simply implementation code:

```python
from typesafe_sdk import Choice, TypeSafeClient

with TypeSafeClient() as client:
    response = client.system_one(
        state=ticket,
        questions={
            "route": Choice(
                instructions="Which team should handle this support request?",
                criteria={
                    "billing": "Billing or refunds",
                    "engineering": "Technical problem or product bug",
                    "sales": "Purchasing or procurement",
                },
            )
        },
    )

route = response.choices["route"]
```

With pyjev, the recurring judgment can instead be declared once, inspected
without credentials, fingerprinted, and shared with CLI automation:

```toml
[decision.ticket-route]
type = "choice"
question = "Which team should handle this support request?"

[decision.ticket-route.options]
billing = "Billing or refunds"
engineering = "Technical problem or product bug"
sales = "Purchasing or procurement"
```

```bash
pyjev decision validate
pyjev decision compile ticket-route --state "example ticket"
```

```python
from pyjev import Jev
from pyjev.pipeline import require_confidence

with Jev() as jev:
    route = jev.decide("ticket-route", state=ticket)

outcome = route | require_confidence(0.85)
```

Both approaches ultimately make a TypeSafe System One request through the
official SDK. pyjev adds value when `ticket-route` is a reusable, inspectable
project contract with an offline compile/fingerprint path and shared Python/CLI
policy conventions. If it is just a one-off implementation detail, the direct
SDK call is simpler.

## When the SDK alone is the better choice

Use `typesafe-sdk` directly when:

- the application has only a few inline System One calls;
- the questions are highly dynamic and do not benefit from a named contract;
- shell/CI reuse or offline declaration validation is not needed;
- no pyjev recipe matches the workflow;
- the application already owns its policy, batch, and output layers;
- low-level SDK request controls are needed; or
- a TypeSafe primitive is not exposed by pyjev.

For example, the current pyjev decision model covers Noul, Choice, Score, and
bundles of those primitives, not TypeSafe's `Box` primitive. Direct SDK use is an
expected escape hatch, not a missing promise of SDK parity.

## What pyjev deliberately does not own

- **Transport and API compatibility:** request execution, retries, authentication,
  assets, API errors, and model/API compatibility remain with `typesafe-sdk`.
- **Every SDK feature:** pyjev is not a complete wrapper for every primitive or
  low-level request option. Use an injected SDK client or `jev.client` when you
  need controls outside pyjev's higher-level surface.
- **Universal policy:** confidence and probability thresholds must be selected and
  calibrated by the caller for the relevant consequences.
- **Application effects:** recipes can return proposals and results, but callers
  own authorization, handlers, and side effects.
- **Governance or guarantees:** a decision fingerprint is not an audit trail,
  tamper-proof control, or correctness guarantee.

If all you need is to issue System One requests, use the SDK. Add pyjev when the
judgment itself needs to become a reusable, inspectable application contract or
workflow.
