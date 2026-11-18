# Comparisons

## pyjev and `typesafe-sdk`

pyjev depends on and delegates to TypeSafe's official Python SDK. They are not
competing transports. Use the SDK to construct and execute System One requests.
Use pyjev when those requests need application-level identity, offline inspection,
reuse across runtime surfaces, explicit interpretation or policy, or packaged
semantic workflows. See [Why pyjev?](why-pyjev.md) for the full product-boundary
explanation.

| Need                                                | `typesafe-sdk`                         | `pyjev`                                                              |
| --------------------------------------------------- | -------------------------------------- | -------------------------------------------------------------------- |
| Make a System One request                           | Yes, the primary API                   | Yes, delegates to the SDK                                            |
| Sync and async clients                              | Yes                                    | Yes, with pyjev decision and recipe APIs                             |
| Typed questions and answers                         | Yes, SDK models                        | Stable pyjev-facing result and workflow contracts around SDK results |
| Low-level retry, transport, and request controls    | Yes                                    | Intentionally delegated to the SDK                                   |
| Named project decisions                             | Build your own application abstraction | `.pyjev.toml` declarations                                           |
| Offline decision validation and request preview     | Build your own tooling                 | `decision validate` and `compile_decision()`                         |
| Deterministic decision-spec fingerprint             | Build your own                         | Yes                                                                  |
| Reuse one named decision from Python and shell/CI   | Build your own                         | Yes                                                                  |
| Shell-safe confidence gate and exit contract        | Build your own                         | Yes                                                                  |
| Inspectable `build -> execute -> interpret` recipes | Cookbook or application code           | Yes                                                                  |
| Bounded, ordered async batch records                | Build your own                         | `pyjev.amap`                                                         |
| Latest or lower-level SDK features                  | Yes                                    | Use the SDK directly when pyjev does not expose them                 |

> **Rule of thumb:** If the call is local implementation detail, the SDK is
> usually enough. If the judgment has a stable name, is reviewed or reused, crosses
> Python and shell/CI boundaries, or needs explicit interpretation and policy,
> pyjev starts to pay for itself.

## Architecture

A named pyjev decision flows through a validated project declaration and back to
the official SDK for execution:

```text
.pyjev.toml -> schema/discovery -> offline compile -> Jev/AsyncJev -> typesafe-sdk
```

The official SDK owns request and response models, transport, retries,
authentication, assets, and API error semantics. pyjev adds declaration,
validation, inspection, result normalization, local interpretation, and caller
policy without becoming a second transport stack. The underlying client remains
available through `jev.client`, and callers can inject an SDK client.

## When to use the SDK directly

Use `typesafe-sdk` directly when:

- the application has only a few inline System One calls;
- the questions are highly dynamic and do not benefit from a named project
  contract;
- shell/CI reuse or offline declaration validation is not needed;
- no pyjev recipe matches the workflow;
- the application already owns its policy, batch, and output layer;
- low-level SDK controls are needed; or
- a TypeSafe primitive is not currently exposed by pyjev.

For example, the current pyjev decision model covers Noul, Choice, Score, and
bundles of those primitives, not TypeSafe's `Box` primitive. The SDK also exposes
lower-level request controls that pyjev intentionally does not mirror. Direct SDK
use is an expected escape hatch, not a promise of complete SDK parity.

## When pyjev pays for itself

Use pyjev when a recurring judgment should be a stable, source-controlled
contract that can be validated and inspected before execution, reused from
Python and automation, or interpreted through explicit caller-owned policy.

Its value is the operational pattern around SDK primitives:

- named declarations and deterministic fingerprints;
- credential-free validation and normalized request previews;
- pyjev result wrappers that preserve uncertainty and response metadata;
- reusable Python pipelines and CLI gate/output conventions;
- semantic recipes with inspectable planning and deterministic interpretation;
- bounded batch records for independent async work.

These features do not claim that pyjev invented typed questions, async execution,
confidence, or bundled requests. The value is a consistent application contract
around those capabilities.

## pyjev and `jev-cli`

This comparison uses `tumf/jev-cli` version **0.6.2**, main commit
`980cb98f5f529ba310ce4c7481a55e034b0a0829`, reviewed on **2026-09-20**. It is a
version-qualified snapshot, not a claim about every future release.

Both projects are useful and overlap on direct Jev primitives. They optimize for
different layers rather than being interchangeable implementations of one
product.

| Use case or capability             | pyjev                                                              | `jev-cli` 0.6.2                                                                              |
| ---------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| Embed Jev in a Python application  | First-class `Jev` API                                              | Primarily a CLI/MCP tool                                                                     |
| Native async Python integration    | `AsyncJev` uses the SDK async client                               | Not its primary API                                                                          |
| Transport boundary                 | Delegates to the official `typesafe-sdk`                           | Direct provider-aware HTTP/request translation                                               |
| Typed application results          | `NoulResult`, `ChoiceResult`, `ScoreResult`, `BundleResult`        | JSON close to the provider/remote contract                                                   |
| Version-controlled named decisions | `.pyjev.toml` with schema and discovery                            | No equivalent named-decision declaration layer                                               |
| Named mixed-question bundles       | Yes                                                                | Raw request capability, without the same declaration layer                                   |
| Offline validation and compilation | Yes; no credential or network required                             | No equivalent named-decision compiler                                                        |
| Confidence-gated automation        | Yes; failed `--value` gates emit no actionable stdout              | No equivalent confidence-policy gate                                                         |
| Credential storage                 | Environment, OS keyring, or explicit plaintext fallback            | Environment or XDG JSON credential store                                                     |
| Generic one-off shell primitives   | `noul`, `choice`, `score`, `run`                                   | `noul`, `choice`, `score`, `run`                                                             |
| State and machine output           | stdin, file, JSON state, `--json`, `--value`                       | stdin, `@file`, JSON state, JSON-first output                                                |
| Providers                          | Official SDK semantics                                             | Official, Vercel AI Gateway, OpenRouter, and custom Jev-compatible endpoint in this baseline |
| MCP host integration               | Not currently                                                      | `jev-mcp` stdio server                                                                       |
| Agent installation workflow        | Not currently                                                      | Bundled `jev install-skills` skill installer                                                 |
| Online credential check            | `auth status` reports local source; `auth test` checks the service | `auth test`                                                                                  |

`jev-cli` retains rich response data where the provider supplies it. pyjev's
result wrappers are a stable Python-facing contract; the distinction is not that
`jev-cli` discards uncertainty.

## pyjev and Nasrallah-AL/jev-cli

This is a separate comparison from the `tumf/jev-cli` section above. It covers
`Nasrallah-AL/jev-cli`, the TypeScript project distributed as npm package `jevctl`
0.2.3, executable `jev`, at main commit
`a1e668164e75d7fc80cc4a51aaeb1d0144d8961f` (reviewed 2026-09-25). It is a dated
snapshot, not a winner/loser ranking or a claim about future releases.

| Capability              | pyjev                                                                | Nasrallah `jev-cli`                                                           |
| ----------------------- | -------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Primary product         | Python application decision layer over the official SDK              | Purpose-built TypeScript CLI/library semantic operations                      |
| Named project contracts | `.pyjev.toml`, offline validation and compilation                    | Different configuration and request-inspection model                          |
| Semantic operations     | Typed primitives and recipes such as `find`, `extract`, and `verify` | `verify`, `classify`, `extract`, `match`, `route`, `find`, `rerank`, and more |
| Generic batch           | Native async `pyjev.amap` with ordered records                       | Batch command and library support                                             |
| Transport boundary      | Official `typesafe-sdk`; no provider translation                     | Provider selection/translation including multiple providers                   |
| Output                  | JSON, confidence-safe `--value`, and structured `--pluck`            | JSON/JSONL and rich pluck/output options                                      |
| Agent workflow          | Inspect-first skill and reusable Python API                          | Skill plus project-specific plugin/hooks                                      |
| Transcript compaction   | Not in pyjev core                                                    | Agent-runtime-oriented compact operation                                      |

The useful lesson is the semantic recipe layer and operational UX, not copying
the external CLI's entire product boundary. pyjev keeps named contracts, offline
inspection, typed uncertainty, explicit caller policy, and the official SDK
transport boundary. Its recipes compose those foundations without invoking
handlers or owning provider behavior.

## Exit codes are not interchangeable

pyjev's exit codes are its own automation contract:

| Exit | pyjev meaning                                                      |
| ---: | ------------------------------------------------------------------ |
|    0 | Successful result and any gate passed                              |
|    1 | Runtime, credential, API, network, or I/O failure                  |
|    2 | Usage or local validation error                                    |
|    3 | Valid Choice/Score result, but the caller's confidence gate failed |

In particular, pyjev exit code `3` means a policy gate failed after Jev returned
a valid result. It does **not** mean the API rejected authentication. Do not use
these numbers as if they were interoperable with another `jev` CLI's taxonomy.
