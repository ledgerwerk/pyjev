from __future__ import annotations

from types import SimpleNamespace

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
