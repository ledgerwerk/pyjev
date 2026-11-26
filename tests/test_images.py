from __future__ import annotations

from types import SimpleNamespace

import pytest
from typesafe_sdk import Image as SDKImage

from pyjev import Image, decide


def test_image_is_the_official_sdk_type() -> None:
    assert Image is SDKImage


def test_top_level_decide_forwards_image_options(monkeypatch) -> None:
    assets = {"<reference>": Image(b"reference image bytes")}
    image_state = {"photo": Image(b"photo image bytes")}
    sentinel = object()
    calls = {}

    class FakeJev:
        def __init__(self, **kwargs):
            calls["init"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

        def decide(self, name, **kwargs):
            calls["decide"] = (name, kwargs)
            return sentinel

    monkeypatch.setattr("pyjev.Jev", FakeJev)

    result = decide("image-check", image_state, model="model", images=True, assets=assets)

    assert result is sentinel
    assert calls["init"] == {"api_key": None, "model": "model", "images": True}
    assert calls["decide"] == (
        "image-check",
        {"state": image_state, "config": None, "model": "model", "assets": assets},
    )


class _Dumpable(SimpleNamespace):
    def model_dump(self, mode="python"):
        del mode
        return dict(self.__dict__)


class _ImageResponse:
    model = "image-test"
    request_id = "image-request"
    usage = _Dumpable(input_tokens=10, output_tokens=2)
    boxes = {
        "answer": _Dumpable(
            box=_Dumpable(top=0.12, bottom=0.77, left=0.06, right=0.22),
            confidence=0.86,
        )
    }
    nouls = {"answer": _Dumpable(noul=0.91)}
    choices = {
        "answer": _Dumpable(
            choice="person",
            confidence=0.93,
            probabilities={"person": 0.93, "other": 0.07},
        )
    }
    scores = {
        "answer": _Dumpable(
            score=2.7,
            confidence=0.88,
            probabilities={0: 0.0, 1: 0.05, 2: 0.2, 3: 0.75},
            legend={0: "low", 1: "normal", 2: "urgent", 3: "critical"},
        )
    }

    def model_dump(self, mode="python"):
        del mode
        return {"model": self.model}


class _SyncImageClient:
    def __init__(self):
        self.calls = []

    def system_one(self, **kwargs):
        self.calls.append(kwargs)
        return _ImageResponse()


class _AsyncImageClient:
    def __init__(self):
        self.calls = []

    async def system_one(self, **kwargs):
        self.calls.append(kwargs)
        return _ImageResponse()


def test_sync_inline_images_use_opt_in_header_and_preserve_result() -> None:
    from pyjev import Jev

    image = Image(b"photo bytes")
    client = _SyncImageClient()
    result = Jev(client=client, images=True).choice(
        ["What is shown in `photo`?", image],
        state={"photo": image},
        choices={"person": image, "other": "Neither"},
    )

    call = client.calls[0]
    question = call["questions"]["answer"]
    assert call["state"]["photo"] is image
    assert question.instructions[1] is image
    assert question.criteria["person"] is image
    assert call["extra_headers"] == {"TypeSafe-Danger-Zone-Images": "true"}
    assert "assets" not in call
    assert result.value == "person"
    assert result.confidence == 0.93


def test_sync_named_assets_are_forwarded_without_default_image_header() -> None:
    from pyjev import Jev

    candidate = Image(b"candidate bytes")
    reference = Image(b"reference bytes")
    assets = {"<reference>": reference}
    client = _SyncImageClient()
    result = Jev(client=client).noul(
        "Does <reference> match `candidate`?",
        state={"candidate": candidate},
        assets=assets,
    )

    call = client.calls[0]
    assert call["state"]["candidate"] is candidate
    assert call["assets"] is assets
    assert call["assets"]["<reference>"] is reference
    assert "extra_headers" not in call
    assert result.value == 0.91


def test_async_inline_images_use_opt_in_header_and_preserve_result() -> None:
    import asyncio

    from pyjev import AsyncJev

    async def run() -> None:
        image = Image(b"photo bytes")
        client = _AsyncImageClient()
        result = await AsyncJev(client=client, images=True).choice(
            ["What is shown in `photo`?", image],
            state={"photo": image},
            choices={"person": image, "other": "Neither"},
        )

        call = client.calls[0]
        question = call["questions"]["answer"]
        assert call["state"]["photo"] is image
        assert question.instructions[1] is image
        assert question.criteria["person"] is image
        assert call["extra_headers"] == {"TypeSafe-Danger-Zone-Images": "true"}
        assert "assets" not in call
        assert result.value == "person"
        assert result.confidence == 0.93

    asyncio.run(run())


def test_async_named_assets_are_forwarded_without_default_image_header() -> None:
    import asyncio

    from pyjev import AsyncJev

    async def run() -> None:
        candidate = Image(b"candidate bytes")
        reference = Image(b"reference bytes")
        assets = {"<reference>": reference}
        client = _AsyncImageClient()
        result = await AsyncJev(client=client).noul(
            "Does <reference> match `candidate`?",
            state={"candidate": candidate},
            assets=assets,
        )

        call = client.calls[0]
        assert call["state"]["candidate"] is candidate
        assert call["assets"] is assets
        assert call["assets"]["<reference>"] is reference
        assert "extra_headers" not in call
        assert result.value == 0.91

    asyncio.run(run())


def test_default_text_request_omits_image_options() -> None:
    from pyjev import Jev

    client = _SyncImageClient()
    Jev(client=client).noul("Question?", state="text only")

    assert set(client.calls[0]) == {"state", "questions", "model"}


def test_sync_decision_methods_forward_named_assets(tmp_path) -> None:
    from pyjev import Jev, NoulDecision

    reference = Image(b"reference bytes")
    assets = {"<reference>": reference}
    client = _SyncImageClient()
    jev = Jev(client=client)
    jev.ask("Question?", state="state", assets=assets)
    jev.noul("Question?", state="state", assets=assets)
    jev.choice("Question?", state="state", choices=["person", "other"], assets=assets)
    jev.score("Question?", state="state", levels=["low", "high"], assets=assets)
    jev.evaluate(NoulDecision("inline", "Question?"), state="state", assets=assets)

    config = tmp_path / ".pyjev.toml"
    config.write_text("[decision.named]\ntype='noul'\nquestion='Question?'\n", encoding="utf-8")
    jev.decide("named", state="state", config=config, assets=assets)
    jev.run(state="state", questions={"answer": {"type": "noul", "instructions": "Question?"}}, assets=assets)

    assert len(client.calls) == 7
    assert all(call["assets"] is assets for call in client.calls)
    assert all("extra_headers" not in call for call in client.calls)


def test_async_decision_methods_forward_named_assets(tmp_path) -> None:
    import asyncio

    from pyjev import AsyncJev, NoulDecision

    async def run() -> None:
        reference = Image(b"reference bytes")
        assets = {"<reference>": reference}
        client = _AsyncImageClient()
        jev = AsyncJev(client=client)
        await jev.ask("Question?", state="state", assets=assets)
        await jev.noul("Question?", state="state", assets=assets)
        await jev.choice("Question?", state="state", choices=["person", "other"], assets=assets)
        await jev.score("Question?", state="state", levels=["low", "high"], assets=assets)
        await jev.evaluate(NoulDecision("inline", "Question?"), state="state", assets=assets)

        config = tmp_path / ".pyjev.toml"
        config.write_text("[decision.named]\ntype='noul'\nquestion='Question?'\n", encoding="utf-8")
        await jev.decide("named", state="state", config=config, assets=assets)
        await jev.run(
            state="state",
            questions={"answer": {"type": "noul", "instructions": "Question?"}},
            assets=assets,
        )

        assert len(client.calls) == 7
        assert all(call["assets"] is assets for call in client.calls)
        assert all("extra_headers" not in call for call in client.calls)

    asyncio.run(run())


def test_sync_box_preserves_structured_request_coordinates_and_assets() -> None:
    from typesafe_sdk import Box as SDKBox

    from pyjev import BoxResult, Jev

    image = Image(b"photo bytes")
    reference = Image(b"reference bytes")
    assets = {"<reference>": reference}
    question = {"target": "mug", "image": "photo"}
    client = _SyncImageClient()

    result = Jev(client=client, images=True).box(question, state={"photo": image}, assets=assets)

    call = client.calls[0]
    sdk_question = call["questions"]["answer"]
    assert isinstance(result, BoxResult)
    assert isinstance(sdk_question, SDKBox)
    assert sdk_question.instructions == question
    assert sdk_question.model_dump(mode="json") == {"type": "box", "instructions": question}
    assert call["state"]["photo"] is image
    assert call["assets"] is assets
    assert call["extra_headers"] == {"TypeSafe-Danger-Zone-Images": "true"}
    assert result.box == {"top": 0.12, "bottom": 0.77, "left": 0.06, "right": 0.22}
    assert result.confidence == 0.86
    assert result.request_id == "image-request"


def test_sync_box_requires_explicit_image_opt_in_before_request() -> None:
    from pyjev import Jev

    client = _SyncImageClient()
    with pytest.raises(ValueError, match="images=True"):
        Jev(client=client).box("the mug", state="photo")
    assert client.calls == []


def test_async_box_requires_explicit_image_opt_in_before_request() -> None:
    import asyncio

    from pyjev import AsyncJev

    async def run() -> None:
        client = _AsyncImageClient()
        with pytest.raises(ValueError, match="images=True"):
            await AsyncJev(client=client).box("the mug", state="photo")
        assert client.calls == []

    asyncio.run(run())


def test_box_decisions_and_raw_questions_require_image_opt_in() -> None:
    from typesafe_sdk import Box

    from pyjev import BoxDecision, BundleDecision, Jev, NoulDecision

    client = _SyncImageClient()
    jev = Jev(client=client)
    with pytest.raises(ValueError, match="images=True"):
        jev.evaluate(BoxDecision("location", "the mug"), state="photo")
    with pytest.raises(ValueError, match="images=True"):
        jev.evaluate(
            BundleDecision(
                "inspection",
                {
                    "visible": NoulDecision("visible", "Is a mug visible?"),
                    "location": BoxDecision("location", "the mug"),
                },
            ),
            state="photo",
        )
    with pytest.raises(ValueError, match="images=True"):
        jev.run(state="photo", questions={"location": Box(instructions="the mug")})
    with pytest.raises(ValueError, match="images=True"):
        jev.run(state="photo", questions={"location": {"type": "box", "instructions": "the mug"}})
    assert client.calls == []


def test_async_box_decision_requires_image_opt_in_before_request() -> None:
    import asyncio

    from pyjev import AsyncJev, BoxDecision

    async def run() -> None:
        client = _AsyncImageClient()
        with pytest.raises(ValueError, match="images=True"):
            await AsyncJev(client=client).evaluate(BoxDecision("location", "the mug"), state="photo")
        assert client.calls == []

    asyncio.run(run())


def test_named_box_decision_executes_with_image_opt_in(tmp_path) -> None:
    from pyjev import BoxResult, Jev

    config = tmp_path / ".pyjev.toml"
    config.write_text(
        '[decision.find-logo]\ntype = "box"\nquestion = { target = "logo", image = "photo" }\n',
        encoding="utf-8",
    )
    client = _SyncImageClient()

    result = Jev(client=client, images=True).decide("find-logo", state={"photo": Image(b"photo")}, config=config)

    assert isinstance(result, BoxResult)
    assert result.box["left"] == 0.06
    assert client.calls[0]["questions"]["answer"].instructions == {"target": "logo", "image": "photo"}
    assert client.calls[0]["extra_headers"] == {"TypeSafe-Danger-Zone-Images": "true"}


def test_async_box_preserves_sdk_question_assets_and_image_header() -> None:
    import asyncio

    from typesafe_sdk import Box as SDKBox

    from pyjev import AsyncJev, BoxResult

    async def run() -> None:
        image = Image(b"photo bytes")
        reference = Image(b"reference bytes")
        assets = {"<reference>": reference}
        question = {"target": "mug", "image": "photo"}
        client = _AsyncImageClient()
        result = await AsyncJev(client=client, images=True).box(
            question,
            state={"photo": image},
            assets=assets,
        )

        call = client.calls[0]
        sdk_question = call["questions"]["answer"]
        assert isinstance(result, BoxResult)
        assert isinstance(sdk_question, SDKBox)
        assert sdk_question.instructions == question
        assert sdk_question.model_dump(mode="json") == {"type": "box", "instructions": question}
        assert call["state"]["photo"] is image
        assert call["assets"] is assets
        assert call["extra_headers"] == {"TypeSafe-Danger-Zone-Images": "true"}
        assert result.box == {"top": 0.12, "bottom": 0.77, "left": 0.06, "right": 0.22}
        assert result.confidence == 0.86
        assert result.request_id == "image-request"

    asyncio.run(run())


def test_public_content_aliases_and_box_types_are_exported() -> None:
    from typesafe_sdk import Content as SDKContent
    from typesafe_sdk import ContentValue as SDKContentValue
    from typesafe_sdk import JSONContent as SDKJSONContent
    from typesafe_sdk import JSONValue as SDKJSONValue

    from pyjev import BoxDecision, BoxResult, Content, ContentValue, JSONContent, JSONValue

    assert Content is SDKContent
    assert ContentValue is SDKContentValue
    assert JSONContent is SDKJSONContent
    assert JSONValue is SDKJSONValue
    assert BoxDecision.__name__ == "BoxDecision"
    assert BoxResult.__name__ == "BoxResult"
