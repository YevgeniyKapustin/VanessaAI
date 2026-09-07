from unittest.mock import AsyncMock, MagicMock

import pytest

from vanessa.core.messages import ImageAttachment
from vanessa.pipeline.vision.describer import SCENE_MAX_CHARS, SceneDescriber


def _response(text: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = text
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.asyncio
async def test_scene_describer_returns_description() -> None:
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=_response("world, two avatars, a shop sign")
    )
    describer = SceneDescriber(client=client, model="vision-test")

    text = await describer.describe(
        ImageAttachment(data_url="data:image/jpeg;base64,AAAA")
    )

    assert text == "world, two avatars, a shop sign"
    call = client.chat.completions.create.await_args
    assert call.kwargs["model"] == "vision-test"
    system = call.kwargs["messages"][0]["content"]
    assert "off-camera" in system or "not in the image" in system
    assert "160" not in system


@pytest.mark.asyncio
async def test_scene_describer_caps_length() -> None:
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_response("x" * 900))
    describer = SceneDescriber(client=client, model="vision-test")

    text = await describer.describe(
        ImageAttachment(data_url="data:image/jpeg;base64,AAAA")
    )

    assert text is not None
    assert len(text) <= SCENE_MAX_CHARS


@pytest.mark.asyncio
async def test_scene_describer_returns_none_on_error() -> None:
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
    describer = SceneDescriber(client=client, model="vision-test")
    assert (
        await describer.describe(
            ImageAttachment(data_url="data:image/jpeg;base64,AAAA")
        )
        is None
    )


@pytest.mark.asyncio
async def test_scene_describer_returns_none_without_data() -> None:
    describer = SceneDescriber(model="vision-test")
    assert await describer.describe(ImageAttachment(data_url="")) is None


@pytest.mark.asyncio
async def test_scene_describer_empty_model_text() -> None:
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_response("   "))
    describer = SceneDescriber(client=client, model="vision-test")
    assert (
        await describer.describe(
            ImageAttachment(data_url="data:image/jpeg;base64,AAAA")
        )
        is None
    )


@pytest.mark.asyncio
async def test_scene_describer_builds_client_when_missing(monkeypatch) -> None:
    created: list[object] = []

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            created.append(kwargs)
            self.chat = MagicMock()
            self.chat.completions.create = AsyncMock(
                return_value=_response("plaza")
            )

    monkeypatch.setattr(
        "vanessa.pipeline.vision.describer.AsyncOpenAI",
        FakeOpenAI,
    )
    describer = SceneDescriber(model="vision-test")
    text = await describer.describe(
        ImageAttachment(data_url="data:image/jpeg;base64,AAAA")
    )
    assert text == "plaza"
    assert created
