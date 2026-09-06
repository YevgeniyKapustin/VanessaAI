from __future__ import annotations

from re import Pattern

from vanessa.config.content import DecisionContent
from vanessa.config.settings import settings
from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.gate.reaction.reaction_gate_prompt import (
    _IMPERATIVE_REQUESTS,
    ReactionGateResult,
    _lower_strip,
    _word_boundary_pattern,
)
from vanessa.pipeline.decision.gate.reaction.reaction_gate_signals import heuristic_yes
from vanessa.pipeline.decision.protocols import NoiseFilterProtocol


def build_reaction_lexicon(
    decision: DecisionContent,
    *,
    question_words: tuple[str, ...] | None,
    trigger_keywords: tuple[str, ...] | None,
    modal_verbs: tuple[str, ...] | None,
    bot_names: tuple[str, ...] | None,
) -> tuple[
    tuple[Pattern[str], ...],
    tuple[str, ...],
    tuple[str, ...],
    frozenset[str],
    tuple[str, ...],
]:
    question_patterns = tuple(
        _word_boundary_pattern(word)
        for word in (question_words if question_words is not None else decision.question_words)
    )
    triggers = tuple(
        _lower_strip(word)
        for word in (
            trigger_keywords
            if trigger_keywords is not None
            else decision.trigger_keywords
        )
        if _lower_strip(word)
    )
    modals = tuple(
        _lower_strip(word)
        for word in (modal_verbs if modal_verbs is not None else decision.modal_verbs)
        if _lower_strip(word)
    )
    if bot_names is not None:
        names = bot_names
    else:
        names = (*decision.default_bot_names, *settings.bot_name_aliases)
    bot_name_set = frozenset(
        name.lower().strip() for name in names if name and name.strip()
    )
    imperative_requests = tuple(sorted(set(_IMPERATIVE_REQUESTS) | set(triggers)))
    return question_patterns, triggers, modals, bot_name_set, imperative_requests


def _heuristic_verdict(
    text: str,
    lowered: str,
    recent_messages: list[ContextMessage],
    sender_telegram_id: int | None,
    *,
    noise_filter: NoiseFilterProtocol,
    bot_names: frozenset[str],
    question_patterns: tuple[Pattern[str], ...],
    imperative_requests: tuple[str, ...],
    modal_verbs: tuple[str, ...],
    continuation_enabled: bool,
    continuation_phrases: tuple[str, ...],
) -> ReactionGateResult | None:
    yes = heuristic_yes(
        text,
        lowered,
        recent_messages,
        sender_telegram_id,
        bot_names=bot_names,
        question_patterns=question_patterns,
        imperative_requests=imperative_requests,
        modal_verbs=modal_verbs,
        continuation_enabled=continuation_enabled,
        continuation_phrases=continuation_phrases,
    )
    if yes is not None:
        return yes
    if noise_filter.is_definite_noise(text):
        return ReactionGateResult(respond=False, reason="heuristic_noise")
    return None


def fast_verdict(
    text: str,
    recent_messages: list[ContextMessage],
    sender_telegram_id: int | None,
    *,
    heuristics_enabled: bool,
    noise_filter: NoiseFilterProtocol,
    bot_names: frozenset[str],
    question_patterns: tuple[Pattern[str], ...],
    imperative_requests: tuple[str, ...],
    modal_verbs: tuple[str, ...],
    continuation_enabled: bool,
    continuation_phrases: tuple[str, ...],
) -> ReactionGateResult | None:
    """Tier-1 zero-cost classification. ``None`` = ambiguous → go to LLM."""
    if not heuristics_enabled:
        return None
    lowered = text.strip().lower()
    if not lowered:
        # Empty body — let the planner decide (fail open, no cost).
        return ReactionGateResult(respond=True, reason="empty")
    return _heuristic_verdict(
        text,
        lowered,
        recent_messages,
        sender_telegram_id,
        noise_filter=noise_filter,
        bot_names=bot_names,
        question_patterns=question_patterns,
        imperative_requests=imperative_requests,
        modal_verbs=modal_verbs,
        continuation_enabled=continuation_enabled,
        continuation_phrases=continuation_phrases,
    )
