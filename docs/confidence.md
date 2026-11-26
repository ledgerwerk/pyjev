# Confidence and policy

Choice, Score, and Box expose several distinct signals:

- the selected option or score value;
- the selected option's probability or score distribution;
- the complete probability distribution;
- `confidence`, as supplied by Jev;
- the application's decision to act.

:::{important}
`ChoiceResult.confidence` is a separate signal from the selected option's probability.
Do not describe it as the probability that the answer is correct.
:::

## Box confidence

`BoxResult.confidence` is separate from the normalized coordinates in `BoxResult.box`. It can be `None` when the SDK response has no confidence value. pyjev preserves `None`; `require_confidence(minimum)` rejects that result when a minimum is required. Missing confidence is not a not-found signal, and Box confidence is not a presence probability. Use a companion Noul when target presence matters, and tune image thresholds on representative examples rather than assuming a universal cutoff.

## Gates

```bash
pyjev choice "Route this ticket" \
  --option billing --option engineering --option sales \
  --min-confidence 0.85 --value
```

A failed gate exits 3. With `--value`, stdout is empty so an unsafe value cannot be
accidentally consumed by a pipeline. Use the exit code to route to human review.

## Thresholds belong to the application

The Python equivalent is a value-level policy outcome rather than a process exit:

```python
from pyjev.pipeline import require_confidence

outcome = result | require_confidence(0.85)
if outcome.passed:
    use_value(outcome.value)
else:
    human_review(outcome.result)
```

Choice, Score, and Box confidence are Jev-supplied signals, not probabilities that an answer is correct. Box gates reject missing confidence. `require_probability()` is separate and applies to a Noul probability of true.

A threshold is invocation policy, not a universal Jev recommendation. Different actions
have different consequences. Keep thresholds at the call site until a deliberate policy
and outcome abstraction exists. pyjev does not add `min_confidence` to `.pyjev.toml` in
this pass, and it does not invent a default threshold.

Noul returns a probability of true and does not expose the Choice/Score/Box confidence gate.
Choose and document an application policy explicitly when using Noul.

The numeric exit codes are part of pyjev's CLI contract, not a Jev or cross-tool
standard. Do not assume they match `jev-cli`; a pyjev exit `3` specifically means
the returned Choice/Score result did not satisfy the caller's threshold.

## Calibrate thresholds and pin models

For calibrated production policy, run representative labeled examples, inspect confidence/probability distributions and error consequences, then record the chosen caller thresholds. Pin an explicit model version for the calibrated workflow and deliberately re-evaluate/re-calibrate before changing that model version; an alias can change underneath a fixed threshold. A pinned model makes version changes visible but does not eliminate data drift or guarantee correctness.
