from dataclasses import dataclass
from typing import Protocol

from app.core.messages import ContextMessage
from app.decision.detectors.intent import IntentResult
from app.decision.models import DecisionResult
from app.decision.detectors.triggers import TriggerResult


@dataclass(frozen=True, slots=True)
class DecisionContext:
    text: str
    telegram_chat_id: int
    recent_messages: list[ContextMessage]
    query_vector: list[float] | None
    intent: IntentResult
    trigger: TriggerResult
    session_active: bool
    relevance_score: float
    should_reply: bool | None = None
    mentions_bot: bool = False
    reply_to_bot: bool = False
    in_listen_window: bool = False

    @property
    def directly_addressed(self) -> bool:
        return self.mentions_bot or self.reply_to_bot


class DecisionRule(Protocol):
    @property
    def needs_relevance(self) -> bool: ...

    def evaluate(self, context: DecisionContext) -> DecisionResult | None: ...
