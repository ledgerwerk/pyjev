#!/usr/bin/env bash
set -euo pipefail

# Read structured state from stdin so no credential or decision data is embedded here.
if recommendation="$(pyjev decide meeting-risk \
  --config "$(dirname "$0")/.pyjev.toml" \
  --state-json \
  --min-confidence 0.85 \
  --value)"; then
  printf 'recommendation=%s\n' "$recommendation"
else
  status=$?
  case "$status" in
    3) printf '%s\n' 'Meeting recommendation is below the confidence gate; ask a human.' >&2 ;;
    *) printf '%s\n' 'Could not obtain a meeting recommendation.' >&2 ;;
  esac
  exit "$status"
fi
