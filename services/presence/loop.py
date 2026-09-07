from __future__ import annotations

import asyncio
import logging

from services.presence.capture import capture_scene_jpeg
from services.presence.models import PresenceReply, PresenceTurn
from services.presence.playback.speak import speak_reply

logger = logging.getLogger(__name__)


def spoken_text(reply: PresenceReply | None) -> str | None:
    if reply is None or reply.action != "reply":
        return None
    text = (reply.text or "").strip()
    if not text:
        return None
    return text


async def handle_turn(turn: PresenceTurn, services) -> None:
    jpeg = await capture_scene_jpeg(grab=services.grab, encode=services.encode)
    filled = PresenceTurn(
        message=turn.message,
        display_name=turn.display_name,
        scene_jpeg=jpeg,
    )
    reply = await services.broker.process(filled)
    text = spoken_text(reply)
    if text is None:
        logger.info("presence_turn_silent")
        return
    await speak_reply(
        text,
        avatar=services.avatar,
        osc=services.osc,
        synthesizer=services.synthesizer,
        player=services.player,
        speaking=services.speaking,
    )


async def run_queue(services) -> None:
    while not services.stop.is_set():
        turn = await asyncio_wait_turn(services)
        if turn is None:
            return
        await _handle_or_log(turn, services)


async def _handle_or_log(turn: PresenceTurn, services) -> None:
    try:
        await handle_turn(turn, services)
    except Exception:
        logger.exception("presence_turn_failed")


async def asyncio_wait_turn(services) -> PresenceTurn | None:
    queue = services.turns
    stop = services.stop
    wait_turn = asyncio.create_task(queue.get())
    wait_stop = asyncio.create_task(stop.wait())
    done, pending = await asyncio.wait(
        {wait_turn, wait_stop},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    if wait_stop in done:
        return None
    return wait_turn.result()
