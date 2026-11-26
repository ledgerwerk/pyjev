# Structured question content

TypeSafe primitives accept more than prose strings. Question instructions, option criteria, and rubrics can be JSON-like objects and arrays. pyjev preserves those values as structure in direct Python calls, named contracts, compiled requests, and fingerprints. Structure changes how a question is described, not the primitive's result type.

The official [`typesafe-sdk` Advanced: structure documentation](https://docs.typesafe.ai/primitives/advanced) defines the upstream behavior. The SDK owns question models, validation, serialization, assets, and transport. pyjev re-exports the SDK's `Content`, `ContentValue`, `JSONContent`, and `JSONValue` aliases without creating a second recursive content type.

`Content` includes text, mappings, arrays, and SDK assets such as `Image`. `JSONContent` is the asset-free JSON form. Named `.pyjev.toml` contracts use JSON-compatible values, not runtime SDK objects or image bytes.

## Where structure is accepted

| Primitive field                  | Structured content                                  |
| -------------------------------- | --------------------------------------------------- |
| Noul question/instructions       | String, object, or array                            |
| Noul `true` and `false` criteria | String, object, or array                            |
| Choice question/instructions     | String, object, or array                            |
| Choice option criteria           | String, object, or array                            |
| Score question/instructions      | String, object, or array                            |
| Score level criteria             | String, object, or array, subject to SDK validation |
| Box question/instructions        | String, object, or array                            |

A structured Choice still returns `ChoiceResult`, a Score returns `ScoreResult`, a Noul returns `NoulResult`, and a Box returns `BoxResult`.

## Direct Python API

Pass mappings and sequences directly. Do not stringify them into a prompt:

```python
from pyjev import Jev

question = {
    "task": "Route the ticket",
    "fields": ["subject", "body"],
}
criteria = {
    "billing": {"covers": ["invoice", "charge", "refund"]},
    "engineering": {"covers": ["bug", "technical failure"]},
}

with Jev() as jev:
    result = jev.choice(question, state=ticket, choices=criteria)
```

The same applies to Noul criteria, Score levels, and Box instructions. Synchronous and native asynchronous methods preserve supported structures. For images inside `Content`, use SDK `Image` values with explicit `images=True`; see [Image inputs](images.md).

## Named decisions in TOML

The `question` field in `.pyjev.toml` may be a string, an inline object, an array, or a nested table. It compiles to TypeSafe's `instructions` field. Choice option values compile to `criteria`; Noul `true` and `false` values also compile to criteria; Score levels become ordered criteria.

```toml
[pyjev]
schema = 1

[decision.ticket-route]
type = "choice"
question = { task = "Route the ticket", fields = ["subject", "body"] }

[decision.ticket-route.options.billing]
covers = ["invoice", "charge", "refund"]

[decision.ticket-route.options.engineering]
covers = ["bug", "technical failure"]
```

Objects keep their keys and arrays keep their order through `decision show --json` and `decision compile`. Existing string declarations and schema version 1 remain supported.

TOML has no native `null` value. Omit optional values where the contract allows it. Do not use magic strings to represent null. Named contracts are source-controlled JSON-compatible data and cannot contain an in-memory SDK `Image` or image bytes. Use textual placeholders in the contract and supply SDK images through `state` or `assets=` at runtime.

## Objects and arrays

Use an object when named fields and relationships help explain the judgment. Use an array when order or membership matters. pyjev preserves object content and sorts object keys only for deterministic fingerprinting. Array order remains significant. Prefer a short prose string when structure would add ceremony without making the contract clearer.

## Box instructions and images

Box is an image-localization primitive, not a new structured-content primitive. Its instructions can also be structured:

```python
from pathlib import Path
from pyjev import Image, Jev

with Jev(images=True) as jev:
    result = jev.box(
        {"target": "coffee mug", "image": "photo"},
        state={"photo": Image(Path("kitchen.jpg"))},
    )
```

Box and image inputs are experimental upstream. Box requests require explicit `images=True`. Box returns one set of normalized coordinates and has no explicit not-found result. When target presence matters, pair Box with a Noul question in a bundle. The CLI supports offline inspection and compilation of Box decisions, but it does not upload images or execute live Box requests.

## Fingerprints and review

A compiled decision fingerprint covers the validated declaration, including nested structured content. Mapping key order does not change the fingerprint, while array order does. Runtime state, credentials, configuration paths, SDK `Image` objects, and runtime `assets=` bytes are not part of the named declaration fingerprint. Review the compiled request and fingerprint before execution when the contract is consequential.

## Validation boundaries

pyjev validates its source-controlled boundary: supported root shapes, JSON/TOML compatibility, declaration fields, and cardinality. It does not duplicate TypeSafe's complete primitive schemas. Official SDK question constructors remain the final primitive-schema validator, and the SDK remains responsible for serialization and request behavior.

## When plain strings are better

Do not turn every one-line question into an object because the API allows it. Structure is useful when labels, fields, or relationships matter and should remain visible in source control. Use concise prose when it communicates the contract more clearly.
