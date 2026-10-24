"""Hermes step of the Retrieve stage: health check, then one worker task.

Hermes is the owner's PC agent behind an SSH tunnel; a run can take up to
100 minutes. This step never waits for an answer: it only checks /health
and queues a ``hermes_ask`` task. The worker posts the late answer.
Fail-open: an offline PC or any error only changes the compose directive.
A result posted lately that already answers the question (``RecentAnswers``)
skips the ask: status "answered", nothing is queued.
"""

from __future__ import annotations

import asyncio
import logging
import time

from vanessa.config.settings import settings
from vanessa.contracts.messages import TaskKind
from vanessa.core.hermes_answers import RecentAnswers
from vanessa.core.protocols import HermesHealthProtocol
from vanessa.core.request_context import get_request_id
from vanessa.infrastructure.broker.dispatcher import TaskDispatcher
from vanessa.infrastructure.observability.metrics import record_hermes_dispatch
from vanessa.infrastructure.observability.metrics.metrics_hermes import (
    record_hermes_answered,
)
from vanessa.pipeline.context import TurnPipelineContext

logger = logging.getLogger("vanessa.pipeline.stages")


def hermes_question(ctx: TurnPipelineContext) -> str:
    plan = ctx.turn_plan
    if plan is None or not plan.ask_hermes:
        return ""
    return plan.hermes_query.strip()


def _telegram_chat_id(ctx: TurnPipelineContext) -> int | None:
    # Only Telegram can receive a late follow-up message (VRChat cannot).
    if ctx.turn.channel != "telegram":
        return None
    return ctx.turn.telegram_chat_id


def hermes_task_payload(
    ctx: TurnPipelineContext, question: str, chat_id: int
) -> dict:
    return {
        "question": question,
        "channel": "telegram",
        "telegram_chat_id": chat_id,
        "telegram_message_id": ctx.turn.telegram_message_id,
        "user_message": ctx.turn.message,
    }


def hermes_dedup_key(ctx: TurnPipelineContext, chat_id: int) -> str:
    turn = ctx.turn
    anchor = turn.telegram_message_id or turn.correlation_id or get_request_id()
    return f"hermes:{chat_id}:{anchor}"


async def _is_online(hermes: HermesHealthProtocol) -> bool:
    try:
        return await asyncio.wait_for(
            hermes.is_online(),
            timeout=settings.hermes_timeout_seconds,
        )
    except TimeoutError:
        return False


async def _ask(
    ctx: TurnPipelineContext,
    hermes: HermesHealthProtocol,
    dispatcher: TaskDispatcher,
    chat_id: int,
) -> str:
    if not await _is_online(hermes):
        return "offline"
    question = hermes_question(ctx)
    dispatcher.submit(
        TaskKind.HERMES_ASK,
        hermes_task_payload(ctx, question, chat_id),
        dedup_key=hermes_dedup_key(ctx, chat_id),
    )
    return "asked"


def _ready(
    hermes: HermesHealthProtocol | None,
    dispatcher: TaskDispatcher | None,
) -> bool:
    return settings.hermes_enabled and hermes is not None and dispatcher is not None


def _answered(
    ctx: TurnPipelineContext, answers: RecentAnswers | None, chat_id: int
) -> bool:
    if answers is None:
        return False
    return answers.covers(chat_id, hermes_question(ctx), ctx.turn.message)


async def run_hermes_step(
    ctx: TurnPipelineContext,
    hermes: HermesHealthProtocol | None,
    dispatcher: TaskDispatcher | None,
    answers: RecentAnswers | None = None,
) -> None:
    """Ask Hermes when the planner flagged the turn; set ``ctx.hermes_status``."""
    chat_id = _telegram_chat_id(ctx)
    if not _ready(hermes, dispatcher) or chat_id is None or not hermes_question(ctx):
        return
    if _answered(ctx, answers, chat_id):
        # The result is already in the chat: the planner repeats the lookup
        # for a reaction to it. A second report would repeat the first one.
        ctx.hermes_status = "answered"
        record_hermes_answered()
        logger.info(
            "turn_stage hermes request_id=%s status=answered", get_request_id()
        )
        return
    await _dispatch(ctx, hermes, dispatcher, chat_id)


async def _dispatch(
    ctx: TurnPipelineContext,
    hermes: HermesHealthProtocol,
    dispatcher: TaskDispatcher,
    chat_id: int,
) -> None:
    started = time.perf_counter()
    try:
        status = await _ask(ctx, hermes, dispatcher, chat_id)
    except Exception:
        # Fail-open: a broken tunnel or broker never blocks the reply.
        logger.exception("hermes_ask_failed request_id=%s", get_request_id())
        status = "error"
    ctx.hermes_status = "asked" if status == "asked" else "offline"
    elapsed_ms = (time.perf_counter() - started) * 1000
    record_hermes_dispatch(status, elapsed_ms)
    logger.info(
        "turn_stage hermes request_id=%s status=%s hermes_ms=%.1f",
        get_request_id(),
        status,
        elapsed_ms,
    )
