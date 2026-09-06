from typing import Protocol

from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.detectors.intent import IntentResult
from vanessa.pipeline.decision.detectors.triggers import TriggerResult
from vanessa.pipeline.decision.models import DecisionResult


class IntentDetectorProtocol(Protocol):
    def detect(self, text: str) -> IntentResult: ...


class TriggerCheckerProtocol(Protocol):
    def detect(self, text: str) -> TriggerResult: ...


class NoiseFilterProtocol(Protocol):
    def is_noise(self, text: str) -> bool: ...

    def is_definite_noise(self, text: str) -> bool: ...


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
        context: DecisionContext,
        *,
        search_text: str | None = None,
        humor_ok: bool = False,
    ) -> DecisionResult: ...

    def record_reply(self, telegram_chat_id: int) -> None: ...
