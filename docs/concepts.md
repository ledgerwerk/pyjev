# Concepts

pyjev exposes a small operational model:

```text
state + typed question -> Jev -> structured answer
```

The SDK supplies the transport and Jev semantics. pyjev adds ergonomic calls,
reusable specifications, local validation, CLI behavior, credentials, and traceable
result wrappers.

## Noul

Noul asks for a yes/no probability. `NoulResult.value` is the probability of true.
pyjev does not silently convert it to `bool`, and Noul does not use the Choice/Score
`confidence` field. Choose an application threshold explicitly if your action needs one.

## Choice

Choice selects one member of a closed set. `ChoiceResult` contains the selected label,
confidence, and the full probability distribution. Criteria can be dynamic:

```python
choices = currently_legal_actions()
result = jev.choice("Which action is best among these?", state=state, choices=choices)
```

Runtime choices do not need to be static project configuration.

## Score

Score evaluates state against ordered levels. The numeric score is the
**probability-weighted position over the ordered levels**. `ScoreResult` also includes
the legend and probability distribution; scores may be fractional.

## Exact logic versus judgment

Keep deterministic facts in ordinary code: legal moves, schema validation, permissions,
and proven tactical exclusions. Use Jev where several valid alternatives require judgment.

> Do not ask a judgment model to rediscover exact facts that ordinary code can compute reliably.

The Connect Four example computes exact legal and tactically losing moves in Python, then
asks Jev to choose among the remaining genuine alternatives. This boundary generalizes to
production systems: deterministic constraints first, ambiguous judgment second.

## Product boundary

```text
application / shell / CI
        pyjev: decisions, confidence-aware output, CLI, credentials, validation
        typesafe-sdk: models, transport, retries, API errors
        Jev API
```

pyjev wraps and preserves TypeSafe/Jev semantics; it does not invent probabilities or
confidence calculations.
