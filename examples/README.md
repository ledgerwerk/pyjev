# pyjev examples

These examples use the public Python API and CLI. They intentionally do not assert
specific Jev outputs: model responses and confidence values can vary. Set
`TYPESAFE_API_KEY` in the environment or configure authentication with `pyjev auth set`;
no example contains a key.

From the repository root:

```bash
python examples/emergency_snack.py
python examples/haunted_ci.py
printf '%s\n' '{"calendar":"quarterly planning","agenda":[],"owner":null}' |
  ./examples/meeting_escape.sh
```

The shared `examples/.pyjev.toml` demonstrates reusable named Noul, Choice, and Score
decisions. The Python examples use a direct Choice and a named Score. The shell example
uses a named Choice with a confidence gate and exits nonzero when human review is needed.
