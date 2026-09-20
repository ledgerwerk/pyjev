# Debugging

Result wrappers preserve the data needed to investigate a decision:

- `request_id` identifies the API request;
- `model` records the selected model;
- `usage` records SDK usage metadata;
- `raw` retains the answer payload;
- `--json` exposes these fields for tooling.

Use named-decision inspection without an API call:

```bash
pyjev decision show ticket-route --json
pyjev decision validate
pyjev decision compile ticket-route --state "Stripe checkout fails"
```

Compilation is the primary request-debugging tool because it shows normalized state,
question criteria, and model selection without credentials or a network call. For the
Connect Four example, `--debug` prints deterministic candidate facts and request metadata;
`--trace PATH` writes credential-free JSONL records.

When debugging a low-confidence result, inspect the complete probability distribution
rather than treating confidence as a correctness guarantee. Also verify that deterministic
application constraints removed invalid choices before asking Jev to judge among the rest.
