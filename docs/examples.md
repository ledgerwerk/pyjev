# Examples

Runnable source lives under `examples/` in the repository. Each example keeps
application policy visible instead of merely printing a model answer.

## Emergency snack

`emergency_snack.py` demonstrates a direct Choice call, structured state, a closed action
set, the full distribution, and an application-level confidence policy.

## Haunted CI

`haunted_ci.py` demonstrates a named Score decision, an ordered rubric, fractional scores,
a legend, and confidence-aware action.

## Connect Four

`connect_four.py` demonstrates deterministic preprocessing, dynamic Choice criteria,
request inspection, and credential-free JSONL tracing. Python computes exact legal moves
and removes moves proven to lose under the example's bounded tactical rules. Jev is called
only when multiple tactically admissible actions remain.

> Deterministic constraints belong in ordinary code; ambiguous judgment among valid
> alternatives belongs in Jev.

Read the full source for the playable demo rather than copying its tactical helpers into
an application without understanding their scope.

## Plain-English semantic linter

`semantic_linter.py` demonstrates a named bundle plus native async fan-out. Standard-library Python AST parsing owns exact file discovery, syntax errors, function boundaries, qualified names, decorators, and source locations. The `semantic-lint` bundle contains 14 independent plain-English Noul rules, and all 14 rules are evaluated in one request for each function.

Independent functions are scheduled concurrently with bounded `AsyncJev` concurrency. The human summary calculates actual function, rule, judgment, and request counts, token usage, and observed elapsed time. JSON output preserves every rule probability and request metadata.

```bash
pyjev decision show semantic-lint --config examples/.pyjev.toml --json
pyjev decision validate --config examples/.pyjev.toml
python examples/semantic_linter.py pyjev/client.py
python examples/semantic_linter.py pyjev/client.py --show-all
python examples/semantic_linter.py pyjev/client.py --json
```

> Batch independent semantic questions about one state into one Jev request; use ordinary async concurrency across independent states.

The default threshold is a demo application policy, not a Jev correctness guarantee. Calibrate it against labeled examples before using this linter as a CI gate. The selected function source is sent to the configured Jev API; do not run it on code you are not permitted to send to that service.

## Emoji Jev

`emoji_jev.py` is an interactive named-bundle example. A single request evaluates a 64-way emoji Choice plus tone questions. The terminal displays the selected emoji, top alternatives from the Choice probability distribution, typed side signals, request metadata, token usage, and client-observed round-trip time.

The top-N display is deterministic Python over Jev's preserved probability distribution; it is not a second model call.
