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

    boxes = {
        "answer": Dumpable(
            box=Dumpable(top=0.12, bottom=0.77, left=0.06, right=0.22),
            confidence=None,
        )
    }

    def __init__(self):
        self.nouls = {"answer": Dumpable(type="noul", noul=0.82)}
        self.choices = {
            "answer": Dumpable(
                type="choice",
                choice="yes",
                confidence=0.9,
                probabilities={"yes": 0.9, "no": 0.1},
            )
        }
        self.scores = {
            "answer": Dumpable(
                type="score",
                score=2.4,
                confidence=0.87,
                probabilities={0: 0.1, 1: 0.2, 2: 0.3, 3: 0.4},
                legend={0: "low", 1: "normal", 2: "urgent", 3: "critical"},
            )
        }

    def model_dump(self, mode: str = "python"):
        del mode
        return {"model": self.model}


class AsyncClient:
    def __init__(self):
        self.calls = []
        self.closed = False

    async def system_one(self, *, state, questions, model=None, **kwargs):
        self.calls.append((state, questions, model))
        self.last_kwargs = kwargs
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


def test_async_box_uses_native_sdk_client_and_preserves_nullable_confidence() -> None:
    async def run() -> None:
        client = AsyncClient()
        image = object()
        assets = {"<reference>": image}
        question = {"target": "mug", "image": "photo"}
        result = await AsyncJev(client=_as_client(client), images=True).box(
            question,
            state={"photo": image},
            assets=assets,
        )

        assert result.box == {"top": 0.12, "bottom": 0.77, "left": 0.06, "right": 0.22}
        assert result.confidence is None
        assert len(client.calls) == 1
        assert client.calls[0][1]["answer"].instructions == question
        assert client.last_kwargs["assets"] is assets
        assert client.last_kwargs["extra_headers"] == {"TypeSafe-Danger-Zone-Images": "true"}

    asyncio.run(run())


def test_async_structured_noul_choice_and_score_content_is_preserved() -> None:
    async def run() -> None:
        client = AsyncClient()
        jev = AsyncJev(client=_as_client(client))
        noul_question = {"task": "Check the sender", "compare": ["name", "email"]}
        true = {"definition": "Identity conflict"}
        false = {"definition": "No material conflict"}
        await jev.noul(noul_question, state={"ticket": "details"}, true=true, false=false)

        choice_question = {"task": "Route", "fields": ["subject", "body"]}
        choices = {"billing": {"covers": ["refund"]}, "engineering": {"covers": ["bug"]}}
        await jev.choice(choice_question, state={"ticket": "details"}, choices=choices)

        score_question = {"task": "Rate urgency", "signals": ["impact", "blocked work"]}
        levels = [{"label": "routine"}, {"label": "critical"}]
        await jev.score(score_question, state={"ticket": "details"}, levels=levels)

        noul_sdk, choice_sdk, score_sdk = (call[1]["answer"] for call in client.calls)
        assert noul_sdk.instructions == noul_question
        assert noul_sdk.criteria == {"true": true, "false": false}
        assert choice_sdk.instructions == choice_question
        assert choice_sdk.criteria == choices
        assert score_sdk.instructions == score_question
        assert score_sdk.criteria == levels

    asyncio.run(run())
