"""Shared local validation helpers for semantic recipes."""

from __future__ import annotations

import math
import re
from typing import Any

_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9._:-]{0,63}\Z")


def validate_id(value: Any, label: str, *, reserved: set[str] | None = None) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} IDs must match [A-Za-z][A-Za-z0-9._:-]{{0,63}}")
    if reserved and value in reserved:
        raise ValueError(f"{label} ID {value!r} is reserved")
    return value


def validate_model(model: str | None) -> None:
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError("model must be a nonempty string or None")


def threshold(value: float, label: str = "threshold") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number between 0 and 1")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 <= normalized <= 1:
        raise ValueError(f"{label} must be a finite number between 0 and 1")
    return normalized


def probability(value: float, label: str = "probability") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid {label}")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 <= normalized <= 1:
        raise ValueError(f"invalid {label}")
    return normalized
