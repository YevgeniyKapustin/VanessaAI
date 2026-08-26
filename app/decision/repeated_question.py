"""RepeatedQuestionRule: skip when the sender repeats a question the bot already answered.

The bot must not repeat the same answer when the same thing is asked again. If the
current message adds no new content compared to an earlier user message that already
got an assistant reply, the turn is ignored (the user already got the answer).

This is a deterministic fallback to the planner's own repeated-question guidance:
it fires only on a near-pure repeat (every content word of the current message was
already in the earlier question), so it won't suppress genuine follow-ups.
"""

from __future__ import annotations

import re

from app.core.messages import ContextMessage
from app.decision.context import DecisionContext
from app.decision.models import DecisionAction, DecisionReason, DecisionResult

_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_STOP = frozenset(
    {
        "ты",
        "тебя",
        "тебе",
        "тобой",
        "твой",
        "твоя",
        "твоё",
        "твое",
        "это",
        "этого",
        "эту",
        "этот",
        "эта",
        "вот",
        "там",
        "тут",
        "здесь",
        "ну",
        "же",
        "ли",
        "бы",
        "и",
        "а",
        "но",
        "или",
        "да",
        "нет",
        "уже",
        "ещё",
        "еще",
        "если",
        "что",
        "как",
        "где",
        "когда",
        "почему",
        "зачем",
        "кто",
        "который",
        "которая",
        "которые",
        "не",
        "ни",
        "то",
        "в",
        "на",
        "по",
        "с",
        "со",
        "к",
        "из",
        "у",
        "для",
        "про",
        "об",
        "обо",
        "о",
        "от",
        "до",
        "при",
    }
)


def message_tokens(text: str) -> set[str]:
    """Content words of a message: lowercased, punctuation stripped, stop words removed."""
    lowered = text.lower().replace("ё", "е")
    cleaned = _PUNCT_RE.sub(" ", lowered)
    words = [word for word in _SPACE_RE.sub(" ", cleaned).split() if len(word) > 1]
    return {word for word in words if word not in _STOP}


def _answered_later(messages: list[ContextMessage], start_index: int) -> bool:
    """Whether the user message at ``start_index`` received an assistant reply."""
    for message in messages[start_index + 1 :]:
        if message.role == "assistant":
            return True
        if message.role == "user":
            return False
    return False


def is_pure_repeat(current: set[str], prior: set[str]) -> bool:
    """A near-pure repeat: current adds no new content and keeps most of the prior.

    ``current`` must be a subset of ``prior`` (no new words) and cover at least 60%
    of it, so shortened re-asks count but genuine expansions do not.
    """
    if len(current) < 3 or not prior:
        return False
    if not current <= prior:
        return False
    return len(current) / len(prior) >= 0.6


class RepeatedQuestionRule:
    """Skip a near-pure repeat of a question the bot already answered."""

    def __init__(self, window: int = 8) -> None:
        self._window = window

    @property
    def needs_relevance(self) -> bool:
        return False

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        recent = context.recent_messages[-self._window :]
        if len(recent) < 2:
            return None
        current = message_tokens(context.text)
        if len(current) < 3:
            return None
        for index, message in enumerate(recent[:-1]):
            if message.role != "user":
                continue
            if not _answered_later(recent, index):
                continue
            prior = message_tokens(message.content)
            if not is_pure_repeat(current, prior):
                continue
            return DecisionResult(
                action=DecisionAction.IGNORE,
                reason=DecisionReason.REPEATED,
                relevance_score=context.relevance_score,
                intent_detected=context.intent.detected,
                trigger_detected=context.trigger.detected,
                session_active=context.session_active,
            )
        return None
