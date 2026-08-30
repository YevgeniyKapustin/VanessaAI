from unittest.mock import AsyncMock, MagicMock

import pytest

from vanessa.config.settings import settings
from vanessa.core.messages import ImageAttachment
from vanessa.pipeline.llm.photo_captioner import PhotoCaptioner


def _response(text: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = text
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.asyncio
async def test_photo_captioner_returns_caption():
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=_response("кот на диване")
    )
    captioner = PhotoCaptioner(client=client, model="vision-test")

    caption = await captioner.generate(
        ImageAttachment(data_url="data:image/jpeg;base64,AAAA")
    )

    assert caption == "кот на диване"
    call = client.chat.completions.create.await_args
    assert call.kwargs["model"] == "vision-test"
    user_content = call.kwargs["messages"][1]["content"]
    assert user_content[0]["type"] == "text"
    assert user_content[1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,AAAA"},
    }


@pytest.mark.asyncio
async def test_photo_captioner_caps_length():
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_response("x" * 500))
    captioner = PhotoCaptioner(client=client, model="vision-test")

    caption = await captioner.generate(
        ImageAttachment(data_url="data:image/jpeg;base64,AAAA")
    )

    assert len(caption) <= settings.vision_photo_caption_max_chars


@pytest.mark.asyncio
async def test_photo_captioner_returns_none_on_error():
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
    captioner = PhotoCaptioner(client=client, model="vision-test")

    assert (
        await captioner.generate(
            ImageAttachment(data_url="data:image/jpeg;base64,AAAA")
        )
        is None
    )


@pytest.mark.asyncio
async def test_photo_captioner_returns_none_without_data():
    captioner = PhotoCaptioner(model="vision-test")
    assert await captioner.generate(ImageAttachment(data_url="")) is None
