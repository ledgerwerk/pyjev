# Agent skill

Use `typesafe-sdk` directly for isolated or low-level System One requests that do not need pyjev's contract, recipe, policy, or automation layers. Prefer pyjev when a judgment has a stable project-level name, must be inspected or validated without execution, should be shared across Python and shell/CI, a recipe encodes the desired semantics, or explicit local review policy matters. pyjev does not replace SDK transport features.
The bundled pyjev skill at `skills/pyjev/SKILL.md` teaches an agent to use
named decision contracts without reading pyjev source or adding an MCP
integration.

See [Why pyjev?](why-pyjev.md) for the product boundary and when direct SDK use is simpler.

Its workflow is deliberately inspect-first:

1. list and show named decisions;
2. validate the complete `.pyjev.toml` locally;
3. compile the exact request without credentials;
4. inspect the schema marker and specification fingerprint;
5. execute only after offline checks succeed;
6. preserve uncertainty and metadata unless a scalar is explicitly safe;
7. apply confidence thresholds as caller policy;
8. keep deterministic constraints in normal application code.

The skill also documents credential-safe setup, `auth test`, and pyjev's
project-specific exit codes. It does not expose a generic primitive MCP server;
a future agent adapter should expose named-decision and offline tooling instead.

## Structured content and Box

Prefer object or array question content when named fields, relationships, or an existing taxonomy become clearer. Keep it structured through direct calls, named schema-1 contracts, inspection, and compilation. Do not serialize objects into prompt strings. Use the official SDK content aliases and let `typesafe-sdk` validate schemas and own serialization and transport.

Box and image requests are experimental upstream. Live Box execution requires `Jev(images=True)` or `AsyncJev(images=True)` with SDK image content. A Box result is one set of coordinates, not a not-found outcome. Add a companion Noul in the same bundle when presence matters; choose thresholds in application policy. Use `typesafe-sdk` directly for lower-level controls not exposed by pyjev. The pyjev CLI supports offline Box inspection and compilation, but not image upload or live Box execution.

## Choosing a pattern

- Stable reusable judgment: declare a named decision in `.pyjev.toml`; validate and compile before executing.
- Runtime-built contract: use `Jev.evaluate()` / `AsyncJev.evaluate()` with typed decision objects.
- Several questions over one state: use a bundle; many independent states: use bounded `pyjev.amap`.
- Candidate search where none may fit: `pyjev.recipes.find` ranks with Choice and judges applicability independently.
- Literal field extraction: `pyjev.recipes.extract` selects only deterministic candidates; inspect candidates and request state before execution.
- Claim/evidence review: `pyjev.recipes.verify` distinguishes `unsupported` from `contradicted` and does not fetch evidence.
- Fixed taxonomies: use `pyjev.recipes.classify`; multi-label mode is independent Noul judgments with an explicit unclear band.
- Entity linkage: use `pyjev.recipes.match` for `same` / `unclear` / `different`, not an overloaded numeric Score.
- Independent candidate relevance: use `pyjev.recipes.rerank`; it is not the competing rank-plus-existence behavior in `find`.
- `pyjev.recipes.screen` is advisory only; preserve all probabilities and never treat `pass` as a security guarantee.
- Route recipes return proposals; they never invoke handlers. Caller thresholds and side effects stay in application code.

Do not flatten a recipe result when review needs its probabilities, confidence, usage, request ID, or raw typed decision. `--pluck` is for structured shell selection and is unavailable if a confidence gate fails; it cannot turn a rejected value into an actionable output.
