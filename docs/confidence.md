# Confidence and policy

Choice and Score expose several distinct signals:

- the selected option or score value;
- the selected option's probability or score distribution;
- the complete probability distribution;
- `confidence`, as supplied by Jev;
- the application's decision to act.

:::{important}
`ChoiceResult.confidence` is a separate signal from the selected option's probability.
Do not describe it as the probability that the answer is correct.
:::

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

Both gates consume the same Choice/Score `confidence` signal. Neither treats that signal as a correctness probability, and a rejected Python outcome still preserves the complete result for review. `require_probability()` is a separate policy for a Noul probability of true.

A threshold is invocation policy, not a universal Jev recommendation. Different actions
have different consequences. Keep thresholds at the call site until a deliberate policy
and outcome abstraction exists. pyjev does not add `min_confidence` to `.pyjev.toml` in
this pass, and it does not invent a default threshold.

Noul returns a probability of true and does not expose the Choice/Score confidence gate.
Choose and document an application policy explicitly when using Noul.

The numeric exit codes are part of pyjev's CLI contract, not a Jev or cross-tool
standard. Do not assume they match `jev-cli`; a pyjev exit `3` specifically means
the returned Choice/Score result did not satisfy the caller's threshold.
