"""RepeatedQuestionRule: skip when the sender repeats a question the bot already answered.

The bot must not repeat the same answer when the same thing is asked again. If the
current message adds no new content compared to an earlier user message that already
got an assistant reply, the turn is ignored (the user already got the answer).

This is a deterministic fallback to the planner's own repeated-question guidance:
it fires only on a near-pure repeat (every content word of the current message was
already in the earlier question), so it won't suppress genuine follow-ups.
"""

from __future__ import annotations

from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.models import (
    DecisionReason,
    DecisionResult,
)
from vanessa.pipeline.decision.repeated_normalize import (
    _MIN_REPEAT_TOKENS,
    _MIN_WINDOW_MESSAGES,
    _answered_later,
    is_pure_repeat,
    is_repeated_message,
    message_tokens,
    normalize_content,
)
from vanessa.pipeline.decision.rule_outcomes import _ignore

__all__ = [
    "RepeatedQuestionRule",
    "is_pure_repeat",
    "is_repeated_message",
    "message_tokens",
    "normalize_content",
]


class RepeatedQuestionRule:
    """Skip a near-pure repeat of a question the bot already answered."""

    def __init__(self, window: int = 8, min_occurrences: int = 2) -> None:
        self._window = window
        self._min_occurrences = max(2, min_occurrences)

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        # Planner already classified this turn as worth a reply (poker "чек",
        # a joke callback, etc.). Do not override that with the burst detector.
        if context.should_reply is True:
            return None
        recent = context.recent_messages[-self._window :]
        if len(recent) < _MIN_WINDOW_MESSAGES:
            return None
        # Same-sender repeated-message spam burst: the same content was sent
        # more than once in the window, regardless of whether it was answered.
        # This is the case the old near-pure-repeat path missed — short spam,
        # rapid bursts, no interleaved assistant reply.
        if is_repeated_message(
            context.text,
            recent,
            sender_telegram_id=context.sender_telegram_id,
            min_occurrences=self._min_occurrences,
        ):
            return _ignore(context, DecisionReason.REPEATED)
        return self._pure_repeat_result(context, recent)

    def _is_answered_pure_repeat(
        self,
        message: ContextMessage,
        index: int,
        recent: list[ContextMessage],
        current: set[str],
    ) -> bool:
        if message.role != "user":
            return False
        if not _answered_later(recent, index):
            return False
        return is_pure_repeat(current, message_tokens(message.content))

    def _pure_repeat_result(
        self,
        context: DecisionContext,
        recent: list[ContextMessage],
    ) -> DecisionResult | None:
        current = message_tokens(context.text)
        if len(current) < _MIN_REPEAT_TOKENS:
            return None
        for index, message in enumerate(recent[:-1]):
            if self._is_answered_pure_repeat(message, index, recent, current):
                return _ignore(context, DecisionReason.REPEATED)
        return None
