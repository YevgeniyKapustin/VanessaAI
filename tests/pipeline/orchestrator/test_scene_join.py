import asyncio

import pytest

from vanessa.core.messages import ImageAttachment
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.orchestrator.scene_join import (
    join_retrieve_and_scene,
    scene_should_run,
)
from vanessa.pipeline.vision.scene import SceneStage


class _Retrieve:
    def __init__(self) -> None:
        self.ran = False

    async def run(self, ctx: TurnPipelineContext) -> bool:
        ctx.rag_ms = 1.0
        self.ran = True
        return True


async def _run_stage(_name: str, coro) -> bool:
    return await coro


def _ctx(*, channel: str, scene_image=None) -> TurnPipelineContext:
    return TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=1 if channel == "telegram" else None,
            message="hi",
            sender_telegram_id=2 if channel == "telegram" else None,
            channel=channel,
            scene_image=scene_image,
        )
    )


def test_telegram_scene_should_not_run() -> None:
    ctx = _ctx(
        channel="telegram",
        scene_image=ImageAttachment(data_url="data:image/jpeg;base64,AAAA"),
    )
    assert scene_should_run(ctx, SceneStage(AsyncDummy())) is False


class AsyncDummy:
    async def describe(self, image):
        del image
        return "seen"


@pytest.mark.asyncio
async def test_telegram_join_is_zero_cost() -> None:
    ctx = _ctx(channel="telegram")
    retrieve = _Retrieve()
    describer = AsyncDummy()
    await join_retrieve_and_scene(
        ctx,
        retrieve=retrieve,
        scene=SceneStage(describer),
        run_stage=_run_stage,
    )
    assert retrieve.ran is True
    assert ctx.scene_description is None


@pytest.mark.asyncio
async def test_vrchat_join_fills_description_before_return() -> None:
    ctx = _ctx(
        channel="vrchat",
        scene_image=ImageAttachment(data_url="data:image/jpeg;base64,AAAA"),
    )
    retrieve = _Retrieve()
    await join_retrieve_and_scene(
        ctx,
        retrieve=retrieve,
        scene=SceneStage(AsyncDummy()),
        run_stage=_run_stage,
    )
    assert retrieve.ran is True
    assert ctx.scene_description == "seen"


class _SlowDescriber:
    async def describe(self, image):
        del image
        await asyncio.sleep(1)
        return "late"


@pytest.mark.asyncio
async def test_scene_timeout_omits_description_and_cancels() -> None:
    ctx = _ctx(
        channel="vrchat",
        scene_image=ImageAttachment(data_url="data:image/jpeg;base64,AAAA"),
    )
    retrieve = _Retrieve()
    await join_retrieve_and_scene(
        ctx,
        retrieve=retrieve,
        scene=SceneStage(_SlowDescriber()),
        run_stage=_run_stage,
        timeout=0.05,
    )
    assert retrieve.ran is True
    assert ctx.scene_description is None


class _BoomDescriber:
    async def describe(self, image):
        del image
        raise RuntimeError("vision down")


@pytest.mark.asyncio
async def test_scene_join_failure_omits_description() -> None:
    ctx = _ctx(
        channel="vrchat",
        scene_image=ImageAttachment(data_url="data:image/jpeg;base64,AAAA"),
    )
    retrieve = _Retrieve()
    await join_retrieve_and_scene(
        ctx,
        retrieve=retrieve,
        scene=SceneStage(_BoomDescriber()),
        run_stage=_run_stage,
    )
    assert retrieve.ran is True
    assert ctx.scene_description is None


def test_scene_should_run_false_without_stage() -> None:
    ctx = _ctx(channel="vrchat")
    assert scene_should_run(ctx, None) is False
