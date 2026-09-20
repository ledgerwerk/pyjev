# Comparisons

## Three layers

- `typesafe-sdk`: the official low-level Python SDK for TypeSafe models, transport,
  retries, and API errors.
- `pyjev`: an operational wrapper with result preservation, named `.pyjev.toml`
  decisions, CLI behavior, credentials, validation, compilation, and confidence gates.
- Other higher-level interfaces: may optimize for application-model or Pydantic ergonomics.

## Why not use the SDK directly?

Use `typesafe-sdk` directly when you want maximum control and do not need named decisions,
pyjev credential ergonomics, the shell CLI, confidence-gate exit semantics, or pyjev result
wrappers. Use pyjev when those operational features make decisions easier to declare,
inspect, validate, execute, gate, trace, and reuse.

pyjev is not a decorator framework, does not require Pydantic, and does not replace the
official SDK's transport or probabilistic semantics.
