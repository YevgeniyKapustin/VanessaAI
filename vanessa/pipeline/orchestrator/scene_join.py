"""Join VRChat scene description with retrieve, then compose.

Scene runs in parallel with retrieve after the gate passes. The join is a
hard barrier before compose so the prompt can read ``ctx.scene_description``.
Telegram (``profile.scene`` off or no screenshot) never starts a task.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.protocols import PipelineStage

logger = logging.getLogger(__name__)

SCENE_JOIN_TIMEOUT = 2.0

StageRunner = Callable[[str, Awaitable[bool]], Awaitable[bool]]


def scene_should_run(ctx: TurnPipelineContext, scene: PipelineStage | None) -> bool:
    if scene is None or not ctx.profile.scene:
        return False
    return ctx.turn.scene_image is not None


async def _cancel_scene(scene_task: asyncio.Task[bool]) -> None:
    scene_task.cancel()
    with suppress(asyncio.CancelledError):
        await scene_task


async def _await_scene(
    ctx: TurnPipelineContext,
    scene_task: asyncio.Task[bool] | None,
    *,
    timeout: float,
) -> None:
    if scene_task is None:
        return
    try:
        await asyncio.wait_for(scene_task, timeout=timeout)
    except TimeoutError:
        await _cancel_scene(scene_task)
        ctx.scene_description = None
        logger.warning("scene_join_timeout timeout=%.1f", timeout)
    except Exception:
        logger.exception("scene_join_failed")
        ctx.scene_description = None


async def join_retrieve_and_scene(
    ctx: TurnPipelineContext,
    *,
    retrieve: PipelineStage,
    scene: PipelineStage | None,
    run_stage: StageRunner,
    timeout: float = SCENE_JOIN_TIMEOUT,
) -> None:
    scene_task: asyncio.Task[bool] | None = None
    if scene_should_run(ctx, scene):
        assert scene is not None
        scene_task = asyncio.create_task(run_stage("scene", scene.run(ctx)))
    await run_stage("retrieve", retrieve.run(ctx))
    await _await_scene(ctx, scene_task, timeout=timeout)
