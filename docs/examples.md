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
