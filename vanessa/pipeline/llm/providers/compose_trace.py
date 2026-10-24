"""Trace records of the compose call (``<LOG_DIR>/trace-<service>.jsonl``).

``compose_prompt`` — system + user prompt once per generate; ``compose_output``
— every API call (``strict`` marks the untagged retry); ``compose_reply`` —
the reply after post-processing (profanity, address, periods).
"""

from __future__ import annotations

from typing import Any

from vanessa.config.settings import settings
from vanessa.infrastructure.observability.trace_log import (
    clip_text,
    report_trace_failure,
    trace_enabled,
    trace_event,
)


def trace_compose_prompt(
    model: str, system: str, user_prompt: str, *, image_count: int = 0
) -> None:
    trace_event(
        "compose_prompt",
        model=model,
        system=system,
        user=user_prompt,
        images=image_count,
    )


def trace_compose_output(
    model: str,
    output: str,
    *,
    strict: bool,
    reasoning_content: str = "",
    finish_reason: str | None = None,
) -> None:
    trace_event(
        "compose_output",
        model=model,
        strict=strict,
        finish_reason=finish_reason,
        output=output,
        reasoning_content=clip_text(
            reasoning_content, settings.trace_log_max_reasoning_chars
        ),
    )


def trace_openai_output(model: str, response: Any, *, strict: bool) -> None:
    """``compose_output`` from an OpenAI-style (DeepSeek) response."""
    if not trace_enabled():
        return
    try:
        choice = response.choices[0]
        message = choice.message
        trace_compose_output(
            model,
            message.content or "",
            strict=strict,
            reasoning_content=getattr(message, "reasoning_content", None) or "",
            finish_reason=getattr(choice, "finish_reason", None),
        )
    except Exception as exc:  # noqa: BLE001 - tracing must never break a turn
        report_trace_failure(exc)


def trace_claude_output(model: str, response: Any, *, strict: bool) -> None:
    """``compose_output`` from an Anthropic response."""
    if not trace_enabled():
        return
    try:
        trace_compose_output(
            model,
            response.content[0].text,
            strict=strict,
            finish_reason=getattr(response, "stop_reason", None),
        )
    except Exception as exc:  # noqa: BLE001 - tracing must never break a turn
        report_trace_failure(exc)


def trace_compose_reply(model: str, reply: str, reasoning: str) -> None:
    trace_event("compose_reply", model=model, reply=reply, reasoning=reasoning)
