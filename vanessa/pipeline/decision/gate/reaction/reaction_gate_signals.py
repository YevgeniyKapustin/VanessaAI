from __future__ import annotations

from re import Pattern

from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.gate.addressing.continuation import (
    is_sender_continuation_demand,
)
from vanessa.pipeline.decision.gate.reaction.reaction_gate_prompt import (
    ReactionGateResult,
)


def _heuristic_question(
    text: str,
    lowered: str,
    question_patterns: tuple[Pattern[str], ...],
) -> bool:
    if text.rstrip().endswith("?"):
        return True
    return any(pattern.search(lowered) for pattern in question_patterns)


def _heuristic_request(
    lowered: str,
    imperative_requests: tuple[str, ...],
    modal_verbs: tuple[str, ...],
) -> bool:
    if any(word in lowered for word in imperative_requests):
        return True
    return any(word in lowered for word in modal_verbs)


def _heuristic_continuation(
    text: str,
    recent_messages: list[ContextMessage],
    sender_telegram_id: int | None,
    *,
    continuation_enabled: bool,
    continuation_phrases: tuple[str, ...],
) -> bool:
    if not continuation_enabled:
        return False
    if not sender_telegram_id:
        return False
    return is_sender_continuation_demand(
        text,
        recent_messages,
        sender_telegram_id,
        phrases=continuation_phrases,
    )


def _heuristic_yes_reason(
    text: str,
    lowered: str,
    recent_messages: list[ContextMessage],
    sender_telegram_id: int | None,
    *,
    question_patterns: tuple[Pattern[str], ...],
    imperative_requests: tuple[str, ...],
    modal_verbs: tuple[str, ...],
    continuation_enabled: bool,
    continuation_phrases: tuple[str, ...],
) -> str | None:
    if _heuristic_question(text, lowered, question_patterns):
        return "heuristic_question"
    if _heuristic_request(lowered, imperative_requests, modal_verbs):
        return "heuristic_request"
    if _heuristic_continuation(
        text,
        recent_messages,
        sender_telegram_id,
        continuation_enabled=continuation_enabled,
        continuation_phrases=continuation_phrases,
    ):
        return "heuristic_continuation"
    return None


def heuristic_yes(
    text: str,
    lowered: str,
    recent_messages: list[ContextMessage],
    sender_telegram_id: int | None,
    *,
    bot_names: frozenset[str],
    question_patterns: tuple[Pattern[str], ...],
    imperative_requests: tuple[str, ...],
    modal_verbs: tuple[str, ...],
    continuation_enabled: bool,
    continuation_phrases: tuple[str, ...],
) -> ReactionGateResult | None:
    first = (
        lowered.split(maxsplit=1)[0].rstrip(",:!?") if lowered.split() else ""
    )
    if first in bot_names:
        return ReactionGateResult(respond=True, reason="heuristic_address")
    reason = _heuristic_yes_reason(
        text,
        lowered,
        recent_messages,
        sender_telegram_id,
        question_patterns=question_patterns,
        imperative_requests=imperative_requests,
        modal_verbs=modal_verbs,
        continuation_enabled=continuation_enabled,
        continuation_phrases=continuation_phrases,
    )
    if reason is None:
        return None
    return ReactionGateResult(respond=True, reason=reason)
