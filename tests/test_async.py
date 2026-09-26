from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

from typesafe_sdk import AsyncTypeSafeClient

from pyjev import AsyncJev, BundleDecision, BundleResult, ChoiceDecision, ChoiceResult, NoulDecision, NoulResult


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


class AsyncBundleResponse:
    model = "async-bundle-model"
    request_id = "async-bundle-request"
    usage = Dumpable(input_tokens=12, output_tokens=5)

    def __init__(self):
        self.nouls = {"exists": Dumpable(type="noul", noul=0.8)}
        self.choices = {
            "best": Dumpable(
                type="choice",
                choice="candidate-a",
                confidence=0.9,
                probabilities={"candidate-a": 0.9, "candidate-b": 0.1},
            )
        }
        self.scores = {}

    def model_dump(self, mode: str = "python"):
        del mode
        return {"model": self.model}


class AsyncBundleClient(AsyncClient):
    async def system_one(self, *, state, questions, model=None):
        self.calls.append((state, questions, model))
        return AsyncBundleResponse()


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


def test_async_evaluate_in_memory_decision_uses_declaration_model():
    async def run() -> None:
        client = AsyncClient()
        jev = AsyncJev(client=_as_client(client))
        decision = ChoiceDecision("answer", "Is this acceptable?", {"yes": None, "no": None}, model="declared")
        result = await jev.evaluate(decision, state="evidence", model="override")
        assert isinstance(result, ChoiceResult)
        assert result.value == "yes"
        assert client.calls[0][2] == "override"
        assert len(client.calls) == 1

    asyncio.run(run())


def test_async_evaluate_bundle_uses_one_request_and_preserves_child_types():
    async def run() -> None:
        client = AsyncBundleClient()
        jev = AsyncJev(client=_as_client(client))
        decision = BundleDecision(
            "find",
            {
                "best": ChoiceDecision("best", "Which candidate?", {"candidate-a": None, "candidate-b": None}),
                "exists": NoulDecision("exists", "Does any candidate answer?"),
            },
        )
        result = await jev.evaluate(decision, state={"query": "item"})
        assert isinstance(result, BundleResult)
        assert isinstance(result.answers["best"], ChoiceResult)
        assert isinstance(result.answers["exists"], NoulResult)
        assert result.request_id == "async-bundle-request"
        assert len(client.calls) == 1

    asyncio.run(run())
