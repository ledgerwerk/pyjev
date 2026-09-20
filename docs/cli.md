# CLI

The CLI is designed for shell composition and stable automation.

## Input sources

Decision commands accept state from `--state`, `--state-file`, or stdin. `--state` and
`--state-file` are mutually exclusive. Add `--state-json` to decode the selected source
as JSON.

## Output modes

- Default output is compact human-readable output.
- `--json` emits structured metadata.
- `--value` emits only the selected value.

`--json` and `--value` cannot be combined.

## Commands

Primitive commands are `ask`/`noul`, `choice`, and `score`. Named decisions use `decide`.
Management commands include `decision list`, `decision show`, `decision validate`, and
`decision compile`. `auth set`, `auth status`, and `auth delete` manage credentials.
`run` is the raw mixed-question escape hatch; `models` lists SDK models.

## Inspection

```bash
pyjev decision list --json
pyjev decision show ticket-route --json
pyjev decision validate
pyjev decision compile ticket-route --state "Stripe checkout fails"
```

Compilation is offline and emits JSON by default. It never includes credentials.

## Confidence gates

Choice and Score support `--min-confidence`. A valid result below the invocation threshold
exits with code 3. With `--value`, failed gates emit no actionable stdout. With `--json`,
the result is wrapped with gate details. Noul exposes probability of true rather than the
Choice/Score confidence signal, so Noul has no confidence gate.

## Exit codes

| Exit | Meaning                                                   |
| ---: | --------------------------------------------------------- |
|    0 | Successful result and any gate passed                     |
|    1 | Runtime, credential, API, network, or I/O failure         |
|    2 | Usage or local validation error                           |
|    3 | Valid Choice/Score result, but the confidence gate failed |

Keep these codes stable in scripts.

## Shell composition

These are pyjev-specific automation codes. They are not interchangeable with
another `jev` CLI's exit-code taxonomy; in particular, pyjev code `3` means a
valid Choice/Score result failed the caller's confidence gate.

```bash
if TEAM="$(cat ticket.txt | pyjev choice "Route this ticket" \
  --option billing --option engineering --option sales \
  --min-confidence 0.85 --value)"; then
  route_to "$TEAM"
else
  case "$?" in
    3) human_review ;;
    *) exit 1 ;;
  esac
fi
```

A failed gate means Jev returned a valid result but the caller's policy did not permit
automated use; it does not mean that the model was universally untrustworthy.
