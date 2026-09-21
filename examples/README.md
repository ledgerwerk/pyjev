# pyjev examples

These examples are deliberately verbose. They are meant to be understandable from
their terminal output without reading the source first.

Set `TYPESAFE_API_KEY` or run `pyjev auth set`, then run from the repository root:

```bash
python examples/emergency_snack.py
python examples/haunted_ci.py
python examples/connect_four.py
python examples/support_triage.py
python examples/semantic_linter.py pyjev/client.py
python examples/semantic_linter.py pyjev --threshold 0.80
python examples/semantic_linter.py pyjev/client.py --show-all
python examples/semantic_linter.py pyjev/client.py --json
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

- `connect_four.py` is an interactive human-vs-Jev game. Python owns exact game
  mechanics and one-ply tactical facts: gravity, legal moves, immediate wins,
  forced blocks, and the board resulting from each candidate. Jev receives that
  structured tactical view and chooses among the remaining genuine alternatives.
  Forced moves do not call Jev because there is no decision to make. When Jev
  does choose, the example prints its selected column, confidence, and complete
  probability distribution over the candidate moves.

- `semantic_linter.py` is the bundle + async example. Python's standard-library AST finds exact function boundaries, including decorators, methods, async functions, and nested functions. The `semantic-lint` named bundle contains 14 plain-English Noul rules; all 14 are evaluated in one request per function, while `AsyncJev` evaluates independent functions concurrently.
  The terminal summary reports actual requests, judgments, token usage, and elapsed time. The reporting threshold is application policy and should be calibrated against labeled examples before using the linter as a CI gate.

  The JSON report preserves every rule probability and request metadata. Use `--fail-on-findings` only when you deliberately want findings at the selected threshold to fail the command.

  The selected function source is sent to the configured Jev API. Do not run the example on code you are not permitted to send to that service.

- `support_triage.py` combines intent routing, composite scoring, confidence-gated actions, and speculative fan-out. The `support-triage` bundle asks all six questions in one request, then ordinary Python chooses the handler. Child confidence remains visible, branch-irrelevant answers are ignored, and the printed attention score uses caller-owned normalization and weights.
  The example is intentionally explainable rather than prescriptive. Thresholds and weights are application policy, and confidence is not a correctness probability.

This split is intentional. Jev is used as a judgment/decision model, not as a
Connect Four board parser or deterministic rules engine. Giving the model
precomputed facts makes the decision interface stronger and keeps exact logic in
ordinary Python.
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

Connect Four deliberately does not confidence-gate Jev's move. Low confidence is
shown to the player, but Jev still has to choose a legal move because uncertainty
is part of the game.

Do not put this decision in `.pyjev.toml`; its options are dynamic.

For the Score example, the numeric result is the probability-weighted position over
ordered levels, so a fractional score is expected and meaningful. The legend and full
probability distribution show what that fraction means. Choosing the nearest level is
application logic in this example, not a Jev rule.

The examples intentionally do not assert specific Jev outputs. Model results and
confidence values may vary. The shared `.pyjev.toml` also contains named Noul and
Choice declarations for CLI experiments.
