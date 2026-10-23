"""Schedule step of the Retrieve stage: add, list or cancel a chat post.

The planner fills ``TurnPlan.schedule``. This step applies it to the store
and sets ``ctx.schedule_note`` so compose confirms it in Vanessa's voice.
The worker posts the scheduled text later. Fail-open: a store error only
changes the directive; the reply still goes out.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from vanessa.config.content_schedule import get_schedule_content
from vanessa.core.protocols import ReminderStoreProtocol
from vanessa.core.request_context import get_request_id
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.schedule_request import ScheduleRequest
from vanessa.pipeline.schedule.actions import (
    ScheduleCall,
    ScheduleOutcome,
    apply_schedule,
)
from vanessa.pipeline.schedule.notes import render_note
from vanessa.pipeline.schedule.timing import schedule_policy

logger = logging.getLogger("vanessa.pipeline.stages")


def schedule_request(ctx: TurnPipelineContext) -> ScheduleRequest | None:
    plan = ctx.turn_plan
    return plan.schedule if plan is not None else None


def _telegram_chat_id(ctx: TurnPipelineContext) -> int | None:
    # Only Telegram chats get posts later (VRChat has no outbound path).
    if ctx.turn.channel != "telegram":
        return None
    return ctx.turn.telegram_chat_id


async def _apply(
    ctx: TurnPipelineContext,
    request: ScheduleRequest,
    store: ReminderStoreProtocol,
    chat_id: int,
) -> ScheduleOutcome:
    call = ScheduleCall(
        request=request,
        chat_id=chat_id,
        source_text=ctx.turn.message,
        now_utc=datetime.now(UTC),
        policy=schedule_policy(),
        sender_id=ctx.turn.sender_telegram_id,
    )
    try:
        return await apply_schedule(call, store)
    except Exception:
        logger.exception("schedule_step_failed request_id=%s", get_request_id())
        return ScheduleOutcome("error")


async def run_schedule_step(
    ctx: TurnPipelineContext, store: ReminderStoreProtocol | None
) -> None:
    """Apply the planner's schedule request; set ``ctx.schedule_note``."""
    request = schedule_request(ctx)
    chat_id = _telegram_chat_id(ctx)
    if store is None or request is None or chat_id is None:
        return
    outcome = await _apply(ctx, request, store, chat_id)
    ctx.schedule_note = render_note(outcome, get_schedule_content(), schedule_policy())
    logger.info(
        "turn_stage schedule request_id=%s action=%s status=%s detail=%s",
        get_request_id(),
        request.action,
        outcome.status,
        outcome.detail,
    )


__all__ = ["run_schedule_step", "schedule_request"]
