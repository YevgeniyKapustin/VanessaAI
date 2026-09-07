from unittest.mock import AsyncMock

import pytest

from vanessa.core.messages import ImageAttachment
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.vision.scene import SceneStage


def _ctx(*, channel: str = "telegram", scene_image=None) -> TurnPipelineContext:
    return TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=1 if channel == "telegram" else None,
            message="hi",
            sender_telegram_id=2 if channel == "telegram" else None,
            channel=channel,
            scene_image=scene_image,
        )
    )


@pytest.mark.asyncio
async def test_scene_stage_skips_telegram() -> None:
    describer = AsyncMock()
    describer.describe = AsyncMock(return_value="a plaza")
    stage = SceneStage(describer)
    ctx = _ctx(
        scene_image=ImageAttachment(data_url="data:image/jpeg;base64,AAAA"),
    )

    assert await stage.run(ctx) is True
    describer.describe.assert_not_awaited()
    assert ctx.scene_description is None


@pytest.mark.asyncio
async def test_scene_stage_skips_without_image() -> None:
    describer = AsyncMock()
    describer.describe = AsyncMock(return_value="a plaza")
    stage = SceneStage(describer)
    ctx = _ctx(channel="vrchat")

    assert await stage.run(ctx) is True
    describer.describe.assert_not_awaited()
    assert ctx.scene_description is None


@pytest.mark.asyncio
async def test_scene_stage_describes_vrchat_screenshot() -> None:
    describer = AsyncMock()
    describer.describe = AsyncMock(return_value="a neon plaza")
    stage = SceneStage(describer)
    image = ImageAttachment(data_url="data:image/jpeg;base64,AAAA")
    ctx = _ctx(channel="vrchat", scene_image=image)

    assert await stage.run(ctx) is True
    describer.describe.assert_awaited_once_with(image)
    assert ctx.scene_description == "a neon plaza"
