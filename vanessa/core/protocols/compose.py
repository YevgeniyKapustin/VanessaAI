from typing import Any, Protocol

from vanessa.core.generate_request import GenerateRequest
from vanessa.core.messages import ContextBlock, ImageAttachment
from vanessa.core.turn import ChatTurnInput, ConversationTurnResult
from vanessa.core.turn_metrics import TurnMetricsSnapshot


class LLMChatCompleter(Protocol):
    """Single-turn chat completion shared by planner / gate / eval.

    ``kind`` labels the caller so token usage and latency are attributable to
    the right stage (planner / memory / metrics / sweep / reaction_gate).
    """

    async def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        kind: str = "completion",
        **kwargs: Any,
    ) -> str: ...


class LLMProviderProtocol(Protocol):
    """Compose LLM. Preferred call is ``generate(GenerateRequest)``.

    Implementations also accept the legacy ``(user_message, context_blocks, **kwargs)``
    surface via ``as_generate_request``.
    """

    async def generate(
        self,
        user_message: str | GenerateRequest,
        context_blocks: list[ContextBlock] | None = None,
        **kwargs: Any,
    ) -> str: ...


class PhotoCaptionerProtocol(Protocol):
    """Generates a short one-line description of a photo (RAG enrichment)."""

    async def generate(self, attachment: ImageAttachment) -> str | None: ...


class IncomingTurnHandlerProtocol(Protocol):
    async def handle_incoming(
        self,
        turn: ChatTurnInput,
    ) -> ConversationTurnResult: ...


class TurnMetricsProtocol(Protocol):
    def record_turn(
        self,
        *,
        action: str,
        reason: str,
        planner_skipped: bool = False,
        deep_search: bool = False,
    ) -> None: ...

    def snapshot(self) -> TurnMetricsSnapshot: ...

    def reset(self) -> None: ...
