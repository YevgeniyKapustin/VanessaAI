from __future__ import annotations

import logging

from vanessa.core.messages import ContextMessage
from vanessa.core.protocols import LLMChatCompleter
from vanessa.pipeline.decision.gate.reaction.reaction_gate_prompt import (
    ReactionGateResult,
    format_recent_messages,
)

logger = logging.getLogger("vanessa.pipeline.decision.gate.reaction_gate")


async def _complete_or_none(
    client: LLMChatCompleter,
    *,
    model: str,
    formatted: str,
    max_tokens: int,
    text: str,
) -> str | None:
    try:
        return (
            await client.complete(
                model,
                [{"role": "user", "content": formatted}],
                kind="reaction_gate",
                max_tokens=max_tokens,
                temperature=0.0,
            )
        ).strip()
    except Exception:
        # Fail-open: a broken classifier must never drop a legitimate turn.
        logger.exception(
            "reaction_gate_failed message=%r, failing open to respond",
            text,
        )
        return None


def _verdict_from_raw(raw: str, text: str) -> ReactionGateResult:
    head = raw.strip().upper()
    if head.startswith("NO"):
        logger.info(
            "reaction_gate_verdict=no message=%r, finalizing without reply",
            text,
        )
        return ReactionGateResult(respond=False, reason="no")
    if head.startswith("YES"):
        return ReactionGateResult(respond=True, reason="yes")
    # Ambiguous (model did not return a clean YES/NO): fail open.
    logger.warning(
        "reaction_gate_ambiguous raw=%r message=%r, failing open to respond",
        raw,
        text,
    )
    return ReactionGateResult(respond=True, reason="ambiguous")


async def classify_with_llm(
    text: str,
    recent_messages: list[ContextMessage],
    *,
    client: LLMChatCompleter | None,
    model: str,
    prompt: str,
    max_tokens: int,
    recent_window: int,
    mentions_bot: bool,
    reply_to_bot: bool,
    reply_to_other_user: bool,
    in_listen_window: bool,
) -> ReactionGateResult:
    if client is None:
        logger.warning(
            "reaction_gate_no_client message=%r, failing open to respond",
            text,
        )
        return ReactionGateResult(respond=True, reason="error")
    formatted = prompt.format(
        message=text,
        recent=format_recent_messages(recent_messages, recent_window),
        mentions_bot="yes" if mentions_bot else "no",
        reply_to_bot="yes" if reply_to_bot else "no",
        reply_to_other_user="yes" if reply_to_other_user else "no",
        listen_window="yes" if in_listen_window else "no",
    )
    logger.info(
        "reaction_gate_request model=%s max_tokens=%s recent=%s "
        "mentions_bot=%s reply_to_bot=%s reply_to_other_user=%s listen_window=%s",
        model,
        max_tokens,
        len(recent_messages),
        mentions_bot,
        reply_to_bot,
        reply_to_other_user,
        in_listen_window,
    )
    raw = await _complete_or_none(
        client,
        model=model,
        formatted=formatted,
        max_tokens=max_tokens,
        text=text,
    )
    if raw is None:
        return ReactionGateResult(respond=True, reason="error")
    return _verdict_from_raw(raw, text)
