"""Bounded, ordered async batch execution for independent pyjev work."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class BatchError:
    """Secret-safe summary of a failed or unscheduled row."""

    kind: Literal["worker_error", "not_started"]
    exception_type: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "exception_type": self.exception_type, "message": self.message}


@dataclass(frozen=True, slots=True)
class BatchRecord(Generic[R]):
    """The outcome for one input row, in original input order."""

    index: int
    id: str
    ok: bool
    result: R | None
    error: BatchError | None
    metadata: Mapping[str, object] | None = None

    def to_dict(self) -> dict[str, Any]:
        value: Any = self.result
        serializer = getattr(value, "to_dict", None)
        if callable(serializer):
            value = serializer()
        return {
            "index": self.index,
            "id": self.id,
            "ok": self.ok,
            "result": value,
            "error": self.error.to_dict() if self.error is not None else None,
            "metadata": dict(self.metadata) if self.metadata is not None else None,
        }


@dataclass(frozen=True, slots=True)
class BatchSummary:
    """Counts and token usage aggregated from successful typed results."""

    total: int
    ok: int
    errors: int
    input_tokens: int
    output_tokens: int

    def to_dict(self) -> dict[str, int]:
        return {
            "total": self.total,
            "ok": self.ok,
            "errors": self.errors,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


@dataclass(frozen=True, slots=True)
class BatchResult(Generic[R]):
    """Ordered batch rows and their aggregate usage summary."""

    records: tuple[BatchRecord[R], ...]
    summary: BatchSummary

    def to_dict(self) -> dict[str, Any]:
        return {"records": [record.to_dict() for record in self.records], "summary": self.summary.to_dict()}


async def amap(
    items: Iterable[T],
    worker: Callable[[T], Awaitable[R]],
    *,
    concurrency: int = 4,
    ids: Sequence[str] | None = None,
    metadata: Sequence[Mapping[str, object] | None] | None = None,
    fail_fast: bool = False,
) -> BatchResult[R]:
    """Run an async worker over inputs with bounded concurrency and ordered results.

    Worker exceptions are captured per row without retaining exception messages, which
    may contain credentials or user data. In fail-fast mode, no new rows are scheduled
    after the first observed worker failure; already-running workers are allowed to
    finish, and unscheduled rows receive ``not_started`` records. Cancelling this
    coroutine cancels all workers and propagates ``CancelledError`` without returning a
    partial batch. This helper adds no retries; SDK retry behavior remains unchanged.

    ``ids`` and ``metadata`` are optional parallel sequences. Without IDs, stable IDs
    ``item-000000`` etc. are generated from input positions. A returned row with
    ``ok=True`` means the worker completed; application policy outcomes (for example,
    a confidence rejection) remain successful results and are not converted to errors.
    """
    if isinstance(concurrency, bool) or not isinstance(concurrency, int) or concurrency < 1:
        raise ValueError("concurrency must be a positive integer")
    if not callable(worker):
        raise TypeError("worker must be callable")
    if not isinstance(fail_fast, bool):
        raise TypeError("fail_fast must be a bool")

    values = list(items)
    row_ids = list(ids) if ids is not None else [f"item-{index:06d}" for index in range(len(values))]
    row_metadata = list(metadata) if metadata is not None else [None] * len(values)
    if len(row_ids) != len(values):
        raise ValueError("ids must have the same length as items")
    if any(not isinstance(row_id, str) or not row_id.strip() for row_id in row_ids):
        raise ValueError("ids must contain nonempty strings")
    if len(set(row_ids)) != len(row_ids):
        raise ValueError("ids must be unique")
    if len(row_metadata) != len(values):
        raise ValueError("metadata must have the same length as items")
    normalized_metadata: list[Mapping[str, object] | None] = []
    for value in row_metadata:
        if value is not None and not isinstance(value, Mapping):
            raise TypeError("metadata rows must be mappings or None")
        normalized_metadata.append(dict(value) if value is not None else None)

    records: list[BatchRecord[R] | None] = [None] * len(values)
    next_index = 0
    stopped = False

    async def run_worker() -> None:
        nonlocal next_index, stopped
        while not stopped and next_index < len(values):
            # No await occurs between the stopped check and assigning a row, so a
            # fail-fast worker prevents later scheduling deterministically.
            index = next_index
            next_index += 1
            try:
                result = await worker(values[index])
            except Exception as exc:
                records[index] = BatchRecord(
                    index=index,
                    id=row_ids[index],
                    ok=False,
                    result=None,
                    error=BatchError(
                        kind="worker_error",
                        exception_type=type(exc).__name__,
                        message="Worker failed; exception details are omitted.",
                    ),
                    metadata=normalized_metadata[index],
                )
                if fail_fast:
                    stopped = True
            else:
                records[index] = BatchRecord(
                    index=index,
                    id=row_ids[index],
                    ok=True,
                    result=result,
                    error=None,
                    metadata=normalized_metadata[index],
                )

    tasks = [asyncio.create_task(run_worker()) for _ in range(min(concurrency, len(values)))]
    try:
        if tasks:
            await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    for index, record in enumerate(records):
        if record is None:
            records[index] = BatchRecord(
                index=index,
                id=row_ids[index],
                ok=False,
                result=None,
                error=BatchError(
                    kind="not_started",
                    exception_type=None,
                    message="Not started after an earlier worker failure.",
                ),
                metadata=normalized_metadata[index],
            )

    complete_records = tuple(record for record in records if record is not None)
    input_tokens = 0
    output_tokens = 0
    for record in complete_records:
        if not record.ok:
            continue
        usage = getattr(record.result, "usage", None)
        if isinstance(usage, Mapping):
            input_tokens += _token_count(usage.get("input_tokens"))
            output_tokens += _token_count(usage.get("output_tokens"))
    ok_count = sum(record.ok for record in complete_records)
    summary = BatchSummary(
        total=len(complete_records),
        ok=ok_count,
        errors=len(complete_records) - ok_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return BatchResult(records=complete_records, summary=summary)


def _token_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value
