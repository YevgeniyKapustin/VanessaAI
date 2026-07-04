from typing import Protocol

from app.core.messages import ContextMessage
from app.decision.detectors.intent import IntentResult
from app.decision.models import DecisionResult
from app.decision.detectors.triggers import TriggerResult


class IntentDetectorProtocol(Protocol):
    def detect(self, text: str) -> IntentResult: ...


class TriggerCheckerProtocol(Protocol):
    def detect(self, text: str) -> TriggerResult: ...


class NoiseFilterProtocol(Protocol):
    def is_noise(self, text: str) -> bool: ...


class SessionWindowProtocol(Protocol):
    def has_active_request(self, messages: list[ContextMessage]) -> bool: ...


class RateLimiterProtocol(Protocol):
    def is_limited(self, chat_id: int) -> bool: ...

    def record_reply(self, chat_id: int) -> None: ...


class RelevanceCheckerProtocol(Protocol):
    async def score(
        self,
        text: str,
        query_vector: list[float] | None = None,
        search_text: str | None = None,
    ) -> float: ...


class DecisionEngineProtocol(Protocol):
    async def decide(
        self,
        text: str,
        telegram_chat_id: int,
        recent_messages: list[ContextMessage],
        query_vector: list[float] | None = None,
        search_text: str | None = None,
        *,
        should_reply: bool | None = None,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
        in_listen_window: bool = False,
    ) -> DecisionResult: ...

    def record_reply(self, telegram_chat_id: int) -> None: ...
