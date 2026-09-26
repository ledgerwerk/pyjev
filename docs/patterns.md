# Decision patterns

`pyjev` supports common decision patterns by combining typed Jev judgments with
ordinary Python policy. Jev evaluates ambiguous questions. The application then
uses the structured results to route work, combine signals, gate automation, or
ignore answers that are not relevant to the selected branch.

The boundary is intentional:

- TypeSafe and Jev provide model evaluation, typed question semantics, result
  probabilities, confidence, and request metadata.
- `pyjev` provides reusable decision declarations, bundles, typed result
  wrappers, offline inspection, and access to preserved uncertainty.
- Application code owns deterministic facts, thresholds, normalization, weights,
  handlers, side effects, and business policy.

## Intent routing

Use a `Choice` question for the intent and route from its selected value. Add
`Score` or `Noul` questions when a branch needs extra signals.

```toml
[decision.ticket-router]
type = "bundle"

[decision.ticket-router.questions.intent]
type = "choice"
question = "What is the primary intent of this customer message?"

[decision.ticket-router.questions.intent.options]
order_status = "Asking about an existing order"
product_question = "Asking about a product before buying"
return_exchange = "Wants to return or exchange something"
complaint = "Unhappy with the experience and wants resolution"

[decision.ticket-router.questions.complexity]
type = "score"
question = "How complex is this request to resolve?"
levels = [
  "Simple lookup or standard procedure",
  "Requires judgment or a multi-step process",
  "Unusual situation, edge case, or escalation needed",
]
```

The bundle is evaluated once, and Python chooses the handler:

```python
from pyjev import BundleResult, ChoiceResult, Jev, ScoreResult

with Jev() as jev:
    result = jev.decide("ticket-router", state={"message": message})

assert isinstance(result, BundleResult)
intent = result.answers["intent"]
complexity = result.answers["complexity"]
assert isinstance(intent, ChoiceResult)
assert isinstance(complexity, ScoreResult)

if intent.confidence < 0.50:
    route_to_human()
elif intent.value == "order_status":
    handle_order_status()
elif intent.value == "complaint" and complexity.value > 1:
    route_to_human()
else:
    handle_intent(intent.value)
```

`pyjev` does not provide a handler registry or a generic router. Invoking a
handler is application behavior, so the application keeps ownership of side
effects, retries, and idempotency.

## Composite scoring

A bundle can ask for several independent `Score` dimensions in one request.
Normalize and combine those dimensions in Python:

```python
weights = {
    "python_depth": 0.40,
    "leadership": 0.10,
    "system_design": 0.40,
    "generalist": 0.10,
}

composite = sum(
    weights[name] * result.answers[name].value / (len(result.answers[name].legend) - 1)
    for name in weights
)
```

`ScoreResult.value` is the probability-weighted position over the ordered
levels, so fractional values are expected. Keep normalization and weights in
application code. They are deterministic policy and do not change the Jev
request or belong in `.pyjev.toml` unless the project deliberately adopts a
broader application-policy DSL.

This keeps the model contract and the business ranking contract separate. The
application can change weights, compare candidates, or define different
policies without changing the atomic Jev questions.

## Confidence-gated routing

`ChoiceResult.confidence` and `ScoreResult.confidence` are preserved separately
from the selected value and probability distribution. Use the signal for the
specific action being considered, with thresholds appropriate to that action:

```python
result = jev.decide("banking-intent", state=command)

if result.confidence < 0.60:
    route_to_support()
elif result.value == "check_balance":
    show_balance()
elif result.value == "approve_transfer" and result.confidence > 0.85:
    approve_transfer()
else:
    ask_user_to_confirm()
```

Confidence is not a correctness probability. It is a model signal that the
caller may use as part of an explicit policy. The CLI exposes
`--min-confidence` for direct Choice and Score decisions and named primitive
decisions. Python policy is the right place for different thresholds per
consequence.

### Result-pipeline form

The same child-specific gate can be expressed with the optional local pipeline API:

```python
from pyjev.pipeline import answer, require_confidence

route_policy = answer("intent") | require_confidence(0.60)
outcome = result | route_policy

if outcome.passed:
    handle_intent(outcome.value)
else:
    route_to_human(outcome.result)
```

This is an ergonomic alternative to the explicit `if` form above. It does not make a network request, dispatch a handler, or add aggregate confidence to a bundle. For a Noul child, use `require_probability(at_least=...)` or `require_probability(at_most=...)` instead of a confidence gate.
Bundles deliberately have no aggregate confidence. A bundle may contain a
high-confidence intent, a low-confidence severity, and another signal with a
different consequence. Gate the child result that controls the action instead
of inventing one bundle threshold. A `NoulResult` also has no Choice or Score
confidence field; use its explicit probability value when that is the relevant
policy signal.

## Speculative fan-out

A named bundle is the first-class speculative fan-out primitive. Put every
potentially useful question in one bundle, send one request for the shared
state, and consume only the answers relevant to the selected route.

```toml
[decision.ticket-triage]
type = "bundle"

[decision.ticket-triage.questions.category]
type = "choice"
question = "What is the category of this ticket?"

[decision.ticket-triage.questions.category.options]
bug = "Technical problem"
billing = "Payment or refund problem"
other = "Another support request"

[decision.ticket-triage.questions.refund-requested]
type = "noul"
question = "The customer explicitly asks for a refund or credit."

[decision.ticket-triage.questions.bug-severity]
type = "score"
question = "How severe is the technical issue?"
levels = ["Minor", "Degraded", "Blocking"]
```

The application can inspect `category`, then use `bug-severity` only for a bug
route and `refund-requested` only for a billing route. Unused answers remain
available in `BundleResult` for diagnostics, but they do not affect a branch
unless application code chooses to use them.

`Jev.run()` and `AsyncJev.run()` remain lower-level dynamic fan-out escape
hatches and return the SDK-shaped response dictionary. Use a named bundle when
the question set is reusable and you want `BundleResult` with typed child
wrappers. Do not silently change the dynamic `run()` return contract.

## Bounded async fan-out

For independent inputs, use `pyjev.amap` rather than writing an unbounded `asyncio.gather` loop. It bounds active work, preserves input order, and represents per-row execution errors without discarding successful results. Each row is a separate worker invocation; use a bundle when several independent questions share one state and should use a single API request. Batch concurrency is operational capacity, not a confidence or correctness policy.

Worker error details are omitted from the serialized `BatchError` to avoid leaking credentials or user data. A successful result that application policy rejects remains `ok=True`; execution status and judgment policy are separate.

## Rank plus applicability

A closed-set `Choice` always returns a winner. When no candidate may apply, combine Choice ranking with an independent `Noul` applicability judgment rather than treating the top Choice probability as proof that a match exists. The `pyjev.recipes.find` helper packages that pattern and retains both results.

## Explicit escape states

If “none applies,” “unknown,” “other,” or “unclear” is a meaningful domain outcome, model it explicitly in the Choice options or another typed question. A low-confidence answer and a confident judgment that none of the options applies are different signals. Do not inject an escape option automatically where it changes the domain semantics.

## Deterministic candidate discovery

For literal extraction, use Python to find source spans and deduplicate/order/cap them; ask Jev only to select among those exact candidates (plus an explicit `none`). Normalize the chosen literal deterministically in Python. This bounds the model's role and keeps the original literal and typed Choice evidence available for review. See [Semantic recipes](recipes.md#extract-deterministic-literal-candidates).

## Taxonomies and entity matching

Use a single `Choice` for exactly one fixed label, adding an explicit `other` option only when that outcome exists in the domain. For independent multi-label classification, use one Noul per label and expose caller-owned positive/negative thresholds; the middle band stays `unclear`. Entity matching is categorical (`same`, `unclear`, `different`), not a numeric score whose weighted position is mistaken for the relation.

## Proposals, independent reranking, and advisory screens

A route helper may return a typed proposal and closed arguments, but the application decides whether to dispatch it; pyjev never calls a handler. Use reranking when each candidate should receive an independent relevance judgment and zero, one, or many may qualify; it is distinct from `find`'s competing Choice plus existence judgment. Semantic screening is advisory only: preserve each signal, calibrate thresholds locally, and never treat `pass` as a security guarantee.

## All four patterns together

`examples/support_triage.py` combines the patterns in one support workflow. Its
`support-triage` bundle asks for intent, complexity, severity, reproducibility,
refund likelihood, and frustration before the route is known. The example then:

1. gates low-confidence intent classifications to a human;
2. sends order-status requests to a deterministic lookup;
3. uses severity confidence, severity score, and reproducibility for bug
   escalation;
4. uses refund probability for billing policy;
5. uses frustration as a cross-cutting priority flag;
6. ignores speculative answers that do not control the selected route.

The example prints the request and result metadata so the one-request fan-out
and the separation between judgment and policy are visible.

## Design boundaries

Do not add a generic `jev.route()` handler framework, aggregate
`bundle.confidence`, or composite weights to the named-decision schema merely to
express these patterns. The reusable library contract is typed judgment plus
preserved uncertainty. Routing, ranking, thresholds, normalization, and side
effects are deterministic application policy and should remain explicit in
Python.
