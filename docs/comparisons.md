# Comparisons

## Three layers

- `typesafe-sdk`: the official low-level Python SDK for TypeSafe models,
  transport, retries, and API errors.
- `pyjev`: a Python application layer with typed results, named `.pyjev.toml`
  decisions, offline compilation, credentials, CLI behavior, and confidence
  gates.
- Other higher-level tools: may optimize for a different application, provider,
  agent, or protocol workflow.

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
result wrappers are a stable Python-facing contract; the distinction is not
that `jev-cli` discards uncertainty.

## Architecture

A pyjev named decision flows through a validated repository declaration:

```text
.pyjev.toml -> schema/discovery -> offline compile -> Jev/AsyncJev -> typesafe-sdk
```

The official SDK owns transport, retries, request models, and API error
semantics. pyjev adds declaration, validation, result normalization, lifecycle,
credentials, and caller policy.

The `jev-cli` baseline is closer to:

```text
CLI or MCP tool -> provider selection/translation -> HTTP endpoint -> JSON result
```

That makes it a strong direct shell, agent, MCP, and multi-provider client. It
also means it owns provider request translation and compatibility behavior.

## When to use which

Use **pyjev** when you need:

- an embeddable sync or async Python client;
- dependency injection and caller-owned client lifecycle;
- typed results with uncertainty and metadata preserved;
- named decisions reviewed in source control;
- credential-free validation or request previews;
- explicit confidence policy at an automation boundary.

Use **`jev-cli`** when you need:

- a standalone generic shell client;
- provider selection across the official service, gateways, or a custom endpoint;
- an MCP server for an agent host;
- its bundled agent-skill installation workflow;
- JSON-first direct request tooling.

For a one-off primitive shell judgment, either tool may fit. The syntax and
output overlap there and should not be treated as the strategic distinction.

## Exit codes are not interchangeable

pyjev's exit codes are its own automation contract:

| Exit | pyjev meaning                                                      |
| ---: | ------------------------------------------------------------------ |
|    0 | Successful result and any gate passed                              |
|    1 | Runtime, credential, API, network, or I/O failure                  |
|    2 | Usage or local validation error                                    |
|    3 | Valid Choice/Score result, but the caller's confidence gate failed |

In particular, pyjev exit code `3` means a policy gate failed after Jev returned a
valid result. It does **not** mean the API rejected authentication. Do not use
these numbers as if they were interoperable with another `jev` CLI's taxonomy.

## Why not use the SDK directly?

Use `typesafe-sdk` directly when you want maximum control and do not need named
decisions, pyjev credential ergonomics, shell-safe confidence gates, offline
inspection, or pyjev result wrappers. Use pyjev when those application and
workflow abstractions make decisions easier to declare, inspect, validate,
execute, gate, trace, and reuse.
