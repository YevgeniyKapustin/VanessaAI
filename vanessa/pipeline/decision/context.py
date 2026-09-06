from dataclasses import dataclass, field
from typing import Protocol

from vanessa.core.messages import ContextMessage
from vanessa.knowledge.metrics.schema import PersonMetrics
from vanessa.pipeline.decision.detectors.intent import IntentResult
from vanessa.pipeline.decision.detectors.triggers import TriggerResult
from vanessa.pipeline.decision.gate.expectation.reply_expectation import (
    mention_warrants_reply,
)
from vanessa.pipeline.decision.models import DecisionResult

_EMPTY_INTENT = IntentResult(detected=False)
_EMPTY_TRIGGER = TriggerResult(detected=False)


@dataclass(frozen=True, slots=True)
class DecisionContext:
    text: str
    telegram_chat_id: int = 0
    recent_messages: list[ContextMessage] = field(default_factory=list)
    query_vector: list[float] | None = None
    intent: IntentResult = _EMPTY_INTENT
    trigger: TriggerResult = _EMPTY_TRIGGER
    session_active: bool = False
    relevance_score: float = 0.0
    should_reply: bool | None = None
    mentions_bot: bool = False
    reply_to_bot: bool = False
    reply_to_other_user: bool = False
    in_listen_window: bool = False
    sender_telegram_id: int = 0
    sender_metrics: PersonMetrics | None = None
    # Loop-repetition signal (see app/decision/repeated_loop.py): how deep the
    # same-topic loop is (0..3) and how annoyed Vanessa is (0..1). High annoyance
    # feeds LowAttitudeRule (maximal ignore tendency) and the cold compose note.
    loop_strength: int = 0
    annoyance: float = 0.0

    @property
    def directly_addressed(self) -> bool:
        return self.mentions_bot or self.reply_to_bot

    @property
    def addressed_with_expectation(self) -> bool:
        """Direct address that implies the sender expects a reply.

        A bare mention is not enough on its own: the message must also signal
        an expected response (question, trigger keyword, imperative/vocative
        request, direct reply to the bot, or planner go-ahead). Covers both
        Telegram-level mentions (mentions_bot / reply_to_bot) and the bot name
        appearing in the text (intent.mentions_bot).
        """
        if not (self.mentions_bot or self.reply_to_bot or self.intent.mentions_bot):
            return False
        return self._mention_warrants_reply()

    @property
    def telegram_addressed_with_expectation(self) -> bool:
        """Like ``addressed_with_expectation`` but only for Telegram-level
        mention entities / replies, not for the bot name merely appearing in
        the text."""
        if not (self.mentions_bot or self.reply_to_bot):
            return False
        return self._mention_warrants_reply()

    def _mention_warrants_reply(self) -> bool:
        return mention_warrants_reply(
            self.text,
            should_reply=self.should_reply,
            reply_to_bot=self.reply_to_bot,
        )


class DecisionRule(Protocol):
    @property
    def needs_relevance(self) -> bool: ...

    def evaluate(self, context: DecisionContext) -> DecisionResult | None: ...
