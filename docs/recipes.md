# Semantic recipes

Semantic recipes package typed pyjev decisions with deterministic input preparation and result interpretation. They are ordinary Python APIs, not a second transport client. Recipe plans can be inspected without credentials or network access; execution uses the caller's existing `Jev` or `AsyncJev` instance. Recipes preserve their underlying typed results so callers can inspect probability distributions, confidence, usage, model, request ID, and raw response data.

Thresholds and actions are caller policy. The examples below use illustrative defaults, not universal correctness thresholds. Calibrate against representative local data and account for the consequences of each action.

## Find: rank and independently test applicability

Use `find` to rank candidate documents or records while separately asking whether any candidate actually answers the query. The Choice ranking alone always has a winner, so it must not be treated as proof that a match exists.

```python
from pyjev import Jev
from pyjev.recipes import Candidate, build_find, execute_find

candidates = [
    Candidate("auth", "API-key resolution and credential precedence."),
    Candidate("client", "Retry behavior in the TypeSafe client."),
    Candidate("release", "Release process and version tagging."),
]

plan = build_find(
    "Where is retry behavior configured?",
    candidates,
    top_k=2,
    found_at=0.70,
    absent_below=0.35,
)
print(plan.to_dict())  # inspect exact state, question specification, and local policy

with Jev() as jev:
    result = execute_find(jev, plan)

if result.exists_verdict == "answered":
    use(result.hits[0])
elif result.exists_verdict == "partial":
    inspect_more(result)
else:
    search_elsewhere()
```

`find` creates one `BundleDecision` with a Choice over candidate IDs (and an explicit no-candidate option) plus an independent Noul applicability judgment. It makes one SDK request. The default result ordering is descending Choice probability, with ties kept in candidate input order. `exists_verdict` is `answered`, `partial`, or `absent`, based only on the Noul probability and caller-supplied thresholds. Even an `absent` verdict retains its ranked hits and the complete `BundleResult` under `result.decision`.

Provide an ordered list or tuple of 1–254 candidates. Candidate IDs must be unique and match `[A-Za-z0-9][A-Za-z0-9._:-]{0,63}`; candidate text must be nonempty. The additional Choice option accounts for the 255-option SDK cardinality bound. Invalid queries, IDs, thresholds, and cardinalities fail before the client is called.

The query and every candidate's ID and text are included in the request state. Inspect `plan.state` or `plan.to_dict()` before execution when privacy or request size matters. There is no silent truncation; callers should bound text and candidate count before calling the recipe. `afind` / `aexecute_find` provide equivalent native-async operation.

## Planning, execution, and interpretation

`build_find` is deterministic and credential-free. `execute_find` performs the API call; `interpret_find` can be tested with a synthetic `BundleResult` without network access. This split makes request shape, interpretation rules, and call count independently testable.

## Policy and limitations

- The probability distribution ranks candidates; a top candidate is not by itself a found/not-found signal.
- Thresholds should be calibrated locally. Confidence and probability values are model signals, not guarantees of correctness.
- The recipe never opens a path, fetches a URL, or dispatches a handler.
- Returned evidence can support application review; it is not a citation guarantee or a substitute for inspecting source material.

## Extract: deterministic literal candidates

Use `extract` only to disambiguate literal values already found by deterministic Python logic. Jev selects among supplied values or an explicit `none` option; it cannot generate a new value.

```python
from pyjev import Jev
from pyjev.recipes import extract, regex_field

field = regex_field(
    name="invoice",
    pattern=r"INV-\d+",
    description="the invoice number",
    normalizer=lambda value: int(value.removeprefix("INV-")),
    max_candidates=32,
)

with Jev() as jev:
    result = extract(
        jev,
        document=invoice_text,
        fields=[field],
        min_confidence=0.85,  # caller policy; calibrate for your use case
    )

invoice = result.fields["invoice"]
if invoice.action == "auto":
    persist(invoice.normalized_value)
elif invoice.action in {"review", "none"}:
    human_review(invoice.source_value, invoice.decision)
```

Regex matches are deduplicated exactly and kept in source order. Every nonempty field produces one Choice in a shared bundle, with stable candidate IDs and an explicit `none` option. Fields with no matches are omitted from the request; if every field is empty, extraction returns `no_candidates` outcomes and makes zero API calls. Candidate caps are explicit per field (default 64, maximum 254); exceeding a cap fails locally rather than silently truncating.

`source_value` is the exact selected literal, while `normalized_value` is produced by the caller's deterministic normalizer. A normalizer exception or non-JSON-compatible output yields `action="review"`, retains the source literal and Choice evidence, and omits the normalized value; exception details are not exposed. Without an explicit `min_confidence`, successful candidate selections default to review rather than automatic action. A below-threshold selection likewise returns review with the original distribution and confidence preserved. `aextract` provides native async execution.

The full document and candidate literals are included in request state. Inspect `build_extract(...).to_dict()` before execution if the document contains sensitive data or may exceed your request budget.

## Verify: support, contradiction, or no coverage

Use `verify` to judge explicit claims against caller-supplied evidence. It deliberately distinguishes contradiction from evidence that says nothing: `supports` maps to `verified`, `contradicts` to `contradicted`, and `says_nothing` to `unsupported`. Unsupported does not mean false.

```python
from pyjev import Jev
from pyjev.recipes import verify

with Jev() as jev:
    report = verify(
        jev,
        claims=[
            ("compat", "The public API remains backwards compatible."),
            ("transport", "The change adds a second provider."),
        ],
        evidence=[
            ("diff", diff_text),
            ("api-docs", api_docs),
        ],
        auto_accept=0.85,  # optional, caller-owned policy
    )

for item in report.results:
    print(item.claim_id, item.verdict, item.confidence, item.probabilities, item.action)
print(report.summary.to_dict())
```

Independent relation questions for claims—and optional evidence-source selection questions when more than one source is supplied—are sent in one bundle request. `auto_accept` never changes the verdict: it only permits `action="auto_accept"` for a `verified` result that meets the caller threshold (and has a confidently selected source when multiple sources were supplied). Contradicted, unsupported, unselected-source, and below-threshold results remain available for review with their original typed Choice results.

Plain claim/evidence strings receive deterministic positional IDs; use `Claim`, `Evidence`, or `(id, text)` pairs for stable caller IDs. IDs are validated and passed through exactly. Plans accept up to 64 claims by default (configurable lower, capped at 64) and 254 evidence sources; over-limit input fails locally instead of silently chunking. The supplied evidence text is included in request state. The recipe does not fetch URLs, guarantee citations, or modify files. Inspect `build_verify(...).to_dict()` before execution when request content or size needs review. `averify` is the native async counterpart.

## Classify: single label, multiple labels, and `other`

For one label, use a closed-set Choice; request the explicit `other` option when items outside the taxonomy are meaningful. `min_confidence` is caller policy. Without it, a single-label result reports `action="review"` rather than implying an automatic action. Multi-label classification is not a Choice: it bundles one independent Noul per label and requires both `positive_at` and `negative_below`; the band between them is returned as `unclear`.

```python
from pyjev import Jev
from pyjev.recipes import Label, build_classify, execute_classify

plan = build_classify(
    "classify this support ticket",
    [Label("billing", "Payment and invoice issues"), Label("technical", "Product failures")],
    include_other=True,
    min_confidence=0.90,  # local policy, calibrated for this workflow
    model="typesafe-model-version",
)
print(plan.to_dict())  # inspect labels, state, questions, and thresholds
with Jev() as jev:
    result = execute_classify(jev, plan)
if result.action == "review":
    send_to_human(result)
elif result.action == "other":
    use_other_queue(result.decision)
else:
    use_label(result.selected_id)
```

`build_classify(..., mode="multi", positive_at=..., negative_below=...)` produces a bundle of independent judgments; any number of labels can be positive. If taxonomy levels depend on a prior answer, walk them explicitly in application code and retain each step result—the next valid option set requires another request. The recipe does not hide that request cost.

## Match: same, unclear, or different

Entity matching uses three categorical Choice outcomes. `unclear` is a real semantic result, not an intermediate Score value. Without `min_confidence`, every result remains `action="review"`; a supplied threshold can yield `auto_match` or `auto_different`, while `unclear` always remains review.

```python
from pyjev import Jev
from pyjev.recipes import build_match, execute_match

plan = build_match(
    "Alice Smith, 1 Main St",
    "A. Smith, 1 Main Street",
    min_confidence=0.92,  # caller-owned
)
with Jev() as jev:
    result = execute_match(jev, plan)
if result.action == "auto_match":
    link_records()
elif result.action == "review":
    inspect(result.decision.probabilities)
```

## Route: propose a handler, never invoke it

`RouteHandler` and `RouteArgument` are descriptions, not imports or callbacks. `build_route` creates one handler Choice plus speculative closed-set argument Choices for every supplied handler in one bounded bundle. `__none__` abstains from routing; `__unspecified__` preserves a missing argument. Only the chosen handler's argument answers are projected into the proposal, while the complete bundle remains available for review.

```python
from pyjev import Jev
from pyjev.recipes import RouteArgument, RouteHandler, build_route, execute_route

handlers = [
    RouteHandler(
        "refund",
        "Start a refund request",
        (RouteArgument("reason", "Refund reason", ("duplicate", "not_received", "other")),),
    ),
    RouteHandler("tracking", "Look up shipment status"),
]
plan = build_route(message, handlers)
print(plan.to_dict())  # includes request text and every allowed argument value
with Jev() as jev:
    proposal = execute_route(jev, plan)
if proposal.status == "proposed" and proposal.arguments_complete:
    application_dispatch(proposal.handler_id, proposal.arguments)  # caller-owned effect
```

The recipe never calls `application_dispatch`, imports a handler, or decides whether a proposal is authorized. Inspect request content before sending; speculative arguments for unselected handlers are still part of the model request. Oversized specs fail locally instead of being truncated.

## Rerank: independent relevance judgments

Use `rerank` when zero, one, or many candidates can be relevant. Unlike `find`, candidates do not compete in one normalized Choice distribution and there is no separate existence question: each candidate receives an independent Noul. The plan splits candidates into deterministic chunks of at most 64, executes chunks sequentially, preserves input order in `results`, and sorts `ranked` by descending relevance probability with input order as the tie-break. The hard plan cap is 4096 candidates; no candidate is silently dropped.

```python
from pyjev import Jev
from pyjev.recipes import RerankCandidate, build_rerank, execute_rerank

plan = build_rerank(
    "Which pages explain retry behavior?",
    [RerankCandidate("client", client_doc), RerankCandidate("guide", guide_doc)],
    chunk_size=64,
    min_relevance=0.72,  # optional caller policy
)
with Jev() as jev:
    result = execute_rerank(jev, plan)
for item in result.ranked:
    print(item.id, item.probability, item.relevant)
```

`min_relevance=None` leaves each `relevant` field unset; probabilities and all per-chunk typed decisions are still preserved. `rerank` is multiple independent judgments, while `find` is competition plus an independent existence judgment.

## Screen: an advisory semantic prefilter

`screen` is a heuristic recipe, not a prompt-injection defense or security boundary. The caller must supply all thresholds through `ScreenPolicy`. The deterministic outcome precedence is: high instruction signal → `block`; low substance or relevance → `skip`; adequate substance plus relevance → `pass`; otherwise `review`. Every signal probability and Noul result is returned, and no client-side gate is installed.

```python
from pyjev import Jev
from pyjev.recipes import ScreenPolicy, build_screen, execute_screen

policy = ScreenPolicy(
    instruction_block_at=0.80,
    substantive_skip_below=0.20,
    relevance_skip_below=0.15,
    relevance_pass_at=0.75,
)
plan = build_screen(untrusted_text, "summarize a release note", policy=policy)
print(plan.to_dict())  # inspect sensitive state and caller policy
with Jev() as jev:
    advisory = execute_screen(jev, plan)
if advisory.outcome in {"block", "review"}:
    apply_application_review_policy(advisory)
```

A `pass` means only that these particular heuristic signals crossed the supplied thresholds. It does not make untrusted content safe. Calibrate against local examples, preserve false-positive/false-negative review, and never use `screen` as the sole security control.
