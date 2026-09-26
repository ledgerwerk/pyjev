"""Central formatting and safe structured selection for public pyjev results."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any


class OutputPathError(ValueError):
    """A structured output selector is invalid or does not exist."""


def to_public_data(value: Any) -> Any:
    """Convert a public result object through its documented ``to_dict`` method."""
    serializer = getattr(value, "to_dict", None)
    return serializer() if callable(serializer) else value


def format_json(value: Any, *, indent: int | None = 2) -> str:
    """Serialize a public value as deterministic JSON."""
    return json.dumps(to_public_data(value), indent=indent, sort_keys=True, ensure_ascii=False)


def format_jsonl(records: Iterable[Any] | Any) -> str:
    """Serialize batch records as one compact JSON object per line."""
    batch_records = getattr(records, "records", None)
    if batch_records is not None:
        records = batch_records
    if isinstance(records, (str, bytes, Mapping)) or not isinstance(records, Iterable):
        raise TypeError("JSONL output requires an iterable of records")
    return "\n".join(
        json.dumps(to_public_data(record), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for record in records
    )


def format_markdown(value: Any, *, title: str = "Result") -> str:
    """Render a concise generic summary without interpreting Jev semantics."""
    data = to_public_data(value)
    lines = [f"# {title}"]
    if isinstance(data, Mapping):
        summary = data.get("summary")
        if isinstance(summary, Mapping):
            lines.extend(["", "## Summary", "", "| Metric | Value |", "| --- | --- |"])
            lines.extend(f"| {_cell(key)} | {_cell(item)} |" for key, item in summary.items())
        records = data.get("records")
        if isinstance(records, (list, tuple)):
            lines.extend(["", "## Records", ""])
            lines.extend(_record_table(records))
        if summary is None and not isinstance(records, (list, tuple)):
            lines.extend(["", "```json", format_json(data), "```"])
    elif isinstance(data, (list, tuple)):
        lines.extend(["", "```json", format_json(data), "```"])
    else:
        lines.extend(["", f"- {_cell(data)}"])
    return "\n".join(lines)


def pluck(value: Any, path: str) -> Any:
    """Select a key/index path from the same dictionary returned by ``to_dict``.

    Dotted mapping keys and nonnegative array indexes (``items[2].id``) are
    supported. Missing keys, invalid syntax, and traversal through a scalar raise
    :class:`OutputPathError`; no miss silently becomes empty output.
    """
    tokens = _parse_path(path)
    current = to_public_data(value)
    for token in tokens:
        if isinstance(token, int):
            if not isinstance(current, (list, tuple)) or token >= len(current):
                raise OutputPathError(f"pluck path {path!r} has no array index [{token}]")
            current = current[token]
        else:
            if not isinstance(current, Mapping) or token not in current:
                raise OutputPathError(f"pluck path {path!r} has no key {token!r}")
            current = current[token]
    return current


def _parse_path(path: str) -> list[str | int]:
    if not isinstance(path, str) or not path:
        raise OutputPathError("pluck path must be a nonempty string")
    tokens: list[str | int] = []
    for segment in path.split("."):
        if not segment:
            raise OutputPathError(f"invalid pluck path {path!r}")
        index = 0
        key_match = re.match(r"[^\[\]]+", segment)
        if key_match is not None:
            tokens.append(key_match.group())
            index = key_match.end()
        while index < len(segment):
            if segment[index] != "[":
                raise OutputPathError(f"invalid pluck path {path!r}")
            end = segment.find("]", index + 1)
            if end < 0:
                raise OutputPathError(f"invalid pluck path {path!r}")
            raw_index = segment[index + 1 : end]
            if not raw_index.isdigit():
                raise OutputPathError(f"pluck path indexes must be nonnegative integers: {path!r}")
            tokens.append(int(raw_index))
            index = end + 1
    if not tokens:
        raise OutputPathError("pluck path must select at least one key or index")
    return tokens


def validate_pluck_path(path: str) -> None:
    """Raise :class:`OutputPathError` for malformed selector syntax."""
    _parse_path(path)


def _record_table(records: list[Any] | tuple[Any, ...]) -> list[str]:
    normalized = [to_public_data(record) for record in records]
    if not normalized:
        return ["No records."]
    keys = ("index", "id", "ok", "error")
    columns = [key for key in keys if any(isinstance(record, Mapping) and key in record for record in normalized)]
    if not columns:
        columns = ["record"]
        rows = [[format_json(record, indent=None)] for record in normalized]
    else:
        rows = [
            [
                format_json(record.get(key), indent=None) if key == "error" else _cell(record.get(key, ""))
                for key in columns
            ]
            for record in normalized
        ]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def _cell(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        text = format_json(value, indent=None)
    else:
        text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")
