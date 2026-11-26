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
pyjev does not silently convert it to `bool`, and Noul does not use the Choice/Score/Box
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

## Box

Box localizes one target in an image and returns normalized `top`, `bottom`, `left`, and `right` coordinates with a separate nullable confidence signal. It has no explicit not-found result. When absence matters, use a companion Noul in the same bundle. Box and image input are experimental upstream and require `images=True`; the official SDK owns the image request and transport.

## Structured content

Structure is orthogonal to primitive type. An object or array can describe a Noul, Choice, Score, or Box instruction or criteria, while the existing primitive result meaning remains unchanged. pyjev preserves that content as structured data rather than converting it to a prompt string. Use structure when named fields or relationships improve clarity; a concise prose question remains appropriate for simple judgments.

## Exact logic versus judgment

Keep deterministic facts in ordinary code: legal moves, schema validation, permissions,
and proven tactical exclusions. Use Jev where several valid alternatives require judgment.

> Do not ask a judgment model to rediscover exact facts that ordinary code can compute reliably.

The Connect Four example computes exact legal and tactically losing moves in Python, then
asks Jev to choose among the remaining genuine alternatives. This boundary generalizes to
production systems: deterministic constraints first, ambiguous judgment second.

## Product boundary

## Product boundary

```text
application effects / policy
        ↑
pyjev: decision identity, reusable recipes, local interpretation/gates,
      output/batch conventions, offline validation/compilation
        ↑
typesafe-sdk: request/response models, sync/async clients, assets,
              retries, transport, authentication, API errors
        ↑
TypeSafe System One API / Jev
```

The key design boundary is that pyjev should make judgments easier to declare, inspect, test, and operationalize without becoming another model API or side-effect framework. TypeSafe and Jev provide the model semantics; the official SDK owns request execution and transport. pyjev adds application-level contracts and workflows around those capabilities. If you only need a few inline requests or low-level SDK controls, use the SDK directly. See [Why pyjev?](why-pyjev.md).
