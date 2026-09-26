from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from pyjev.batch import BatchResult, amap


@dataclass
class ResultWithUsage:
    value: int
    usage: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "usage": self.usage}


def test_amap_bounds_concurrency_and_preserves_input_order() -> None:
    async def run() -> None:
        active = 0
        maximum = 0

        async def worker(value: int) -> int:
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep((5 - value) * 0.001)
            active -= 1
            return value * 10

        result = await amap(range(6), worker, concurrency=2)
        assert maximum == 2
        assert [record.result for record in result.records] == [0, 10, 20, 30, 40, 50]
        assert [record.index for record in result.records] == list(range(6))
        assert [record.id for record in result.records] == [f"item-{index:06d}" for index in range(6)]

    asyncio.run(run())


def test_amap_captures_row_errors_without_exposing_exception_text_and_sums_usage() -> None:
    async def run() -> None:
        async def worker(value: int) -> ResultWithUsage:
            if value == 1:
                raise RuntimeError("credential=private-secret")
            return ResultWithUsage(value, {"input_tokens": 3, "output_tokens": 2})

        result = await amap(
            [0, 1, 2],
            worker,
            concurrency=2,
            ids=["a", "b", "c"],
            metadata=[{"row": 0}, None, {"row": 2}],
        )
        assert isinstance(result, BatchResult)
        assert [record.ok for record in result.records] == [True, False, True]
        assert result.records[1].error is not None
        assert result.records[1].error.exception_type == "RuntimeError"
        assert "private-secret" not in repr(result.to_dict())
        assert result.records[0].metadata == {"row": 0}
        assert result.summary.total == 3
        assert result.summary.ok == 2
        assert result.summary.errors == 1
        assert result.summary.input_tokens == 6
        assert result.summary.output_tokens == 4

    asyncio.run(run())


@pytest.mark.parametrize("concurrency", [0, -1, True, 1.5])
def test_amap_rejects_invalid_concurrency(concurrency: object) -> None:
    async def run() -> None:
        with pytest.raises(ValueError, match="positive integer"):
            await amap([], _unused_worker, concurrency=concurrency)  # type: ignore[arg-type]

    asyncio.run(run())


async def _unused_worker(value: Any) -> Any:
    return value


def test_amap_rejects_invalid_ids_and_metadata_before_scheduling() -> None:
    async def run() -> None:
        with pytest.raises(ValueError, match="unique"):
            await amap([1, 2], _unused_worker, ids=["same", "same"])
        with pytest.raises(ValueError, match="same length"):
            await amap([1], _unused_worker, metadata=[])

    asyncio.run(run())


def test_amap_fail_fast_keeps_inflight_rows_and_marks_unscheduled_rows() -> None:
    async def run() -> None:
        started: list[int] = []
        second_started = asyncio.Event()

        async def worker(value: int) -> int:
            started.append(value)
            if value == 0:
                await second_started.wait()
                raise RuntimeError("sensitive detail")
            if value == 1:
                second_started.set()
                await asyncio.sleep(0.005)
            return value

        result = await amap(range(5), worker, concurrency=2, fail_fast=True)
        assert started == [0, 1]
        assert result.records[0].error is not None
        assert result.records[0].error.kind == "worker_error"
        assert result.records[1].ok
        assert all(record.error is not None and record.error.kind == "not_started" for record in result.records[2:])

    asyncio.run(run())


def test_amap_cancellation_cancels_workers_and_propagates() -> None:
    async def run() -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def worker(value: int) -> int:
            del value
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        task = asyncio.create_task(amap([1], worker))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()

    asyncio.run(run())


def test_amap_empty_input_returns_empty_summary() -> None:
    async def run() -> None:
        result = await amap([], _unused_worker)
        assert result.records == ()
        assert result.summary.total == 0
        assert result.summary.ok == 0
        assert result.summary.errors == 0

    asyncio.run(run())
