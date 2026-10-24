"""Trace record of the Retrieve stage: what compose will see, with its text."""

from __future__ import annotations

from typing import Any

from vanessa.core.messages import ContextMessage
from vanessa.infrastructure.observability.trace_log import (
    report_trace_failure,
    trace_enabled,
    trace_event,
)
from vanessa.knowledge.schema import KnowledgeBlock
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.llm.prompts.session_format import session_context_messages
from vanessa.pipeline.stages.retrieve_hermes import hermes_question


def _message(message: ContextMessage) -> dict[str, Any]:
    """One chat line without image bytes."""
    return {
        "id": message.id,
        "role": message.role,
        "sender": message.sender_name,
        "at": message.created_at.isoformat() if message.created_at else None,
        "text": message.content,
        "reply_to": message.reply_to_text,
        "photo": message.photo_caption,
    }


def _block(block: KnowledgeBlock) -> dict[str, Any]:
    return {"path": block.path, "title": block.title, "text": block.content}


def trace_retrieve(ctx: TurnPipelineContext) -> None:
    """Hermes ask, web, pinned / knowledge notes, memes, session and earlier lines."""
    if not trace_enabled():
        return
    try:
        _trace(ctx)
    except Exception as exc:  # noqa: BLE001 - tracing must never break a turn
        report_trace_failure(exc)


def _trace(ctx: TurnPipelineContext) -> None:
    plan = ctx.turn_plan
    earlier = ctx.session.earlier_messages if ctx.session else []
    trace_event(
        "retrieve",
        hermes_status=ctx.hermes_status,
        hermes_query=hermes_question(ctx),
        web_query=plan.web_query if plan and plan.web_search else "",
        web=ctx.web_blocks,
        knowledge=[_block(block) for block in ctx.knowledge_blocks],
        schedule_note=ctx.schedule_note,
        memes=[meme.name for meme in [*ctx.meme_blocks, *ctx.meme_menu]],
        session=[_message(item) for item in session_context_messages(ctx.recent)],
        earlier=[_message(item) for item in earlier],
    )
