# pyjev examples

These examples are deliberately verbose. They are meant to be understandable from
their terminal output without reading the source first.

Set `TYPESAFE_API_KEY` or run `pyjev auth set`, then run from the repository root:

```bash
python examples/emergency_snack.py
python examples/haunted_ci.py
```

Jev evaluates **state + a typed question** and returns structured data rather than
free-form text.

- `emergency_snack.py` uses a direct `Choice`. It prints the state, allowed options,
  selected label, complete probability distribution, confidence, and a tiny
  confidence-gated application policy. A Choice is a closed-set decision, so Python
  can inspect every allowed alternative without parsing model prose.
- `haunted_ci.py` uses the named `haunted-ci` `Score` from `.pyjev.toml`. It shows
  that a Score can be fractional, prints the ordered legend and level probabilities,
  and demonstrates how ordinary Python can decline to act when confidence is low.

The examples intentionally show the boundary between Jev/TypeSafe and pyjev:

- TypeSafe supplies state evaluation, Choice and Score semantics, the selected answer
  or score, probabilities, confidence, and model response metadata.
- pyjev supplies the `Jev` Python client, direct primitive calls, named decisions from
  `.pyjev.toml`, and convenient typed result fields such as `value`, `probabilities`,
  `legend`, and `request_id`. It wraps and preserves TypeSafe's semantics; it does
  not invent the probability or confidence calculations.

Confidence is useful as an input to ordinary deterministic application policy. The
thresholds in these examples are teaching examples, not universal recommendations:
a program can automate a low-stakes action when confidence clears its threshold and
otherwise leave the decision to a human. Confidence is separate from the selected
option's probability and should not be described as the probability that an answer is
correct.

For the Score example, the numeric result is the probability-weighted position over
ordered levels, so a fractional score is expected and meaningful. The legend and full
probability distribution show what that fraction means. Choosing the nearest level is
application logic in this example, not a Jev rule.

The examples intentionally do not assert specific Jev outputs. Model results and
confidence values may vary. The shared `.pyjev.toml` also contains named Noul and
Choice declarations for CLI experiments.
