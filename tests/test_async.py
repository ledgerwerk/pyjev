from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

from typesafe_sdk import AsyncTypeSafeClient

from pyjev import AsyncJev


class Dumpable(SimpleNamespace):
    def model_dump(self, mode: str = "python"):
        del mode
        return dict(self.__dict__)


class AsyncResponse:
    model = "async-test"
    request_id = "async-request"
    usage = Dumpable(input_tokens=4, output_tokens=2)

    def __init__(self):
        self.nouls = {}
        self.choices = {
            "answer": Dumpable(
                type="choice",
                choice="yes",
                confidence=0.9,
                probabilities={"yes": 0.9, "no": 0.1},
            )
        }
        self.scores = {}

    def model_dump(self, mode: str = "python"):
        del mode
        return {"model": self.model}


class AsyncClient:
    def __init__(self):
        self.calls = []
        self.closed = False

    async def system_one(self, *, state, questions, model=None):
        self.calls.append((state, questions, model))
        return AsyncResponse()

    async def aclose(self):
        self.closed = True


def _as_client(client: AsyncClient) -> AsyncTypeSafeClient:
    return cast(AsyncTypeSafeClient, client)


def test_async_choice_uses_native_async_client():
    async def run() -> None:
        client = AsyncClient()
        jev = AsyncJev(client=_as_client(client))
        result = await jev.choice("Choose", state="state", choices=["yes", "no"])
        assert result.value == "yes"
        assert len(client.calls) == 1
        await jev.close()
        assert client.closed is False

    asyncio.run(run())
