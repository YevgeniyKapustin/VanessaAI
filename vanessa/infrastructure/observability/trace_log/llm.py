"""Trace hook at the chat-completer boundary (planner, gates, worker LLM calls).

Inside a turn (a ``request_id`` is set) the record holds the full messages
and output. Background calls (sweep, portraits, metrics, scheduled posts)
have no turn: they get one compact record each.
"""

from __future__ import annotations

from typing import Any

from vanessa.config.settings import settings
from vanessa.core.request_context import get_request_id
from vanessa.infrastructure.observability.trace_log import (
    clip_text,
    report_trace_failure,
    trace_enabled,
    trace_event,
)

# ``request_id_var`` default: no turn in this context.
NO_REQUEST = "-"
COMPACT_OUTPUT_CHARS = 600


def trace_llm_call(
    *,
    provider: str,
    model: str,
    kind: str,
    messages: list[dict[str, Any]],
    output: str = "",
    reasoning: str = "",
    usage: dict[str, int] | None = None,
    error: str | None = None,
) -> None:
    """One record per completion; never raises."""
    if not trace_enabled():
        return
    try:
        head = {"provider": provider, "model": model, "usage": usage, "error": error}
        if get_request_id() == NO_REQUEST:
            trace_event(kind, **head, **_compact(messages, output))
            return
        trace_event(
            kind,
            **head,
            messages=messages,
            output=output,
            reasoning_content=clip_text(
                reasoning, settings.trace_log_max_reasoning_chars
            ),
        )
    except Exception as exc:  # noqa: BLE001 - tracing must never break a call
        report_trace_failure(exc)


def _compact(messages: list[dict[str, Any]], output: str) -> dict[str, Any]:
    return {
        "compact": True,
        "prompt_chars": sum(len(str(item.get("content", ""))) for item in messages),
        "output": clip_text(output, COMPACT_OUTPUT_CHARS),
    }
