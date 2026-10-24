"""Trace records of one Hermes job, keyed by the turn that asked.

The bot builds a turn ``request_id`` as ``<chat_id>:<message_id>``; the job
uses the same key, so ``scripts/trace_turn.py`` shows the turn and its late
follow-up together. The retell LLM call is traced by the completer hook.
"""

from __future__ import annotations

from services.worker.hermes.html_file import HtmlFile
from services.worker.hermes.payload import HermesAsk
from vanessa.core.request_context import chat_id_var, request_id_var
from vanessa.infrastructure.observability.trace_log import trace_event


def turn_request_id(ask: HermesAsk) -> str:
    if ask.telegram_message_id is None:
        return ask.idempotency_key
    return f"{ask.telegram_chat_id}:{ask.telegram_message_id}"


def bind_job(ask: HermesAsk) -> None:
    """Set the turn keys for this job (its own asyncio task context)."""
    request_id_var.set(turn_request_id(ask))
    chat_id_var.set(ask.telegram_chat_id)


def trace_query(ask: HermesAsk, instructions: str | None) -> None:
    trace_event(
        "hermes_query",
        question=ask.question,
        user_message=ask.user_message,
        instructions=instructions,
    )


def trace_answer(answer: str | None, outcome: str) -> None:
    trace_event("hermes_answer", outcome=outcome, answer=answer)


def trace_sent(blocks: list[str], file: HtmlFile | None) -> None:
    trace_event(
        "hermes_sent",
        parts=blocks,
        file=file.file_name if file else None,
        file_bytes=file.size_bytes if file else 0,
    )
