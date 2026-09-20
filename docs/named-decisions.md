# Named decisions

`.pyjev.toml` is a version-controlled decision specification, not a secret store.
Keep credentials in the environment, keyring, or user-level credential file.

## Schema

Canonical files declare schema 1:

```toml
[pyjev]
schema = 1
```

A missing `[pyjev]` table remains accepted as legacy implicit schema 1. Unknown schema
fields, non-integer values, and unsupported schema numbers fail during local validation.
No migration machinery is implied by the marker.

## Primitive declarations

```toml
[decision.ticket-route]
type = "choice"
question = "Which team should handle this?"
model = "jev-latest"

[decision.ticket-route.options]
billing = "Billing or refunds"
engineering = "Technical problem"
sales = "Purchasing question"

[decision.urgency]
type = "score"
question = "How urgent is this?"
levels = ["Can wait", "Normal", "Urgent", "Critical"]
```

Noul uses `true` and `false` criteria. Choice requires 2–255 options; Score requires
2–10 ordered levels. Unknown fields and invalid criteria are rejected before API access.

## Bundles

A bundle asks several independent typed questions about one state in one SDK request:

```toml
[decision.ticket-triage]
type = "bundle"

[decision.ticket-triage.questions.refund]
type = "noul"
question = "Does the customer request a refund?"

[decision.ticket-triage.questions.route]
type = "choice"
question = "Which team should handle this?"

[decision.ticket-triage.questions.route.options]
billing = "Billing issue"
engineering = "Technical issue"
sales = "Purchase question"
```

Child keys become answer identifiers. Nested bundles and child `model` fields are not
allowed initially because one `system_one()` request uses one model. Model precedence is
explicit call model, then bundle model, then the client/SDK default.

Bundle results preserve every child result's probabilities and confidence, plus shared
model, usage, raw response, and request ID. Bundles have no aggregate confidence policy;
`--value` and `--min-confidence` are rejected.

## Compiled output contract

`decision compile` produces a credential-free JSON preview with this stable top-level shape:

```json
{
  "schema": 1,
  "decision": {
    "name": "ticket-route",
    "type": "choice",
    "config": ".pyjev.toml",
    "fingerprint": "<sha256>"
  },
  "request": { "state": "...", "questions": {}, "model": null }
}
```

The `schema` marker is the compiled-output contract version. `decision.name`,
`decision.type`, `decision.config`, `decision.fingerprint`, and the request fields
are stable contract fields. The config identifier is relative to the current
project when possible and otherwise uses the config filename; it is never an
absolute machine path. Question and answer data retain the official SDK shape.

The SHA-256 `fingerprint` identifies the validated decision specification and
schema. It includes the decision name, type, criteria, model, and declaration
content. It excludes runtime `state`, credentials, and environment-specific
absolute paths, so the same declaration has the same fingerprint in different
checkouts. Compilation remains local: it does not construct a client, read a
credential, or contact the API.

## Discovery and inspection

Configuration precedence is explicit `config=`/`--config`, then `PYJEV_CONFIG`, then the
nearest `.pyjev.toml` in the current directory or a parent. Use `decision validate` to
check all declarations without a network call and `decision compile` to inspect a
normalized request for a particular state.

## When not to use named decisions

Do not put a decision in `.pyjev.toml` when its criteria are inherently dynamic at runtime.
For example, Connect Four legal actions depend on the current board; build those choices
in Python after deterministic filtering.
