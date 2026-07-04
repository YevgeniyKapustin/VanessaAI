from datetime import datetime
from typing import TYPE_CHECKING, Protocol, TypedDict

from app.core.messages import ContextBlock, ContextMessage, StoredMessage
from app.core.turn import ChatTurnInput, ConversationTurnResult

if TYPE_CHECKING:
    from app.services.turn_metrics import TurnMetricsSnapshot

class VectorSearchHit(TypedDict):
    message_id: int
    score: float


class UnitOfWorkProtocol(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class MessageRepositoryProtocol(Protocol):
    async def create(
        self,
        role: str,
        content: str,
        sender_telegram_id: int | None = None,
        qdrant_point_id: str | None = None,
        created_at: datetime | None = None,
        telegram_message_id: int | None = None,
    ) -> StoredMessage: ...

    async def fulltext_search(
        self,
        query: str,
        limit: int = 30,
    ) -> list[StoredMessage]: ...

    async def get_by_ids(self, message_ids: list[int]) -> list[StoredMessage]: ...

    async def get_conversation_window_blocks(
        self,
        anchor_ids: list[int],
        before: int = 10,
        after: int = 10,
        max_total: int = 80,
    ) -> list[tuple[int, list[StoredMessage]]]: ...

    async def get_recent(self, limit: int = 50) -> list[StoredMessage]: ...

    async def get_existing_telegram_message_ids(
        self,
        telegram_message_ids: list[int],
    ) -> set[int]: ...

    async def update_qdrant_point_id(
        self,
        message_id: int,
        point_id: str,
    ) -> None: ...


class EmbeddingProviderProtocol(Protocol):
    async def embed(self, text: str) -> list[float]: ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class VectorStoreProtocol(Protocol):
    async def ensure_collection(self) -> None: ...

    async def upsert_message(
        self,
        message_id: int,
        role: str,
        content: str,
        vector: list[float],
        point_id: str | None = None,
    ) -> str: ...

    async def upsert_batch(
        self,
        items: list[tuple[int, list[float], str | None]],
    ) -> list[str]: ...

    async def search(
        self,
        vector: list[float],
        limit: int = 30,
    ) -> list[VectorSearchHit]: ...


class TurnQueryProtocol(Protocol):
    async def embed_query(self, query: str) -> list[float]: ...


class ContextRetrieverProtocol(Protocol):
    async def search(
        self,
        query: str,
        top_k: int | None = None,
        query_vector: list[float] | None = None,
        skip_fts: bool = False,
        anchor_max: int | None = None,
        fts_query: str | None = None,
        semantic_queries: list[str] | None = None,
        window_before: int | None = None,
        window_after: int | None = None,
    ) -> list[ContextBlock]: ...


class MessageIndexerProtocol(Protocol):
    async def index(
        self,
        message_id: int,
        role: str,
        content: str,
        point_id: str | None = None,
    ) -> str: ...


class MessageIndexingSchedulerProtocol(Protocol):
    async def index_now(self, record: StoredMessage) -> None: ...

    def schedule(self, record: StoredMessage) -> None: ...


class LLMProviderProtocol(Protocol):
    async def generate(
        self,
        user_message: str,
        context_blocks: list[ContextBlock],
        session_messages: list[ContextMessage] | None = None,
        humor_quotes: list[str] | None = None,
        *,
        sender_telegram_id: int | None = None,
        sender_name: str | None = None,
        system_prompt: str | None = None,
    ) -> str: ...


class IncomingTurnHandlerProtocol(Protocol):
    async def handle_incoming(
        self,
        turn: ChatTurnInput,
    ) -> ConversationTurnResult: ...


class ChatUserProtocol(Protocol):
    nickname: str | None
    first_name: str | None
    username: str | None


class UserRepositoryProtocol(Protocol):
    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> ChatUserProtocol: ...


class TurnMetricsProtocol(Protocol):
    def record_turn(
        self,
        *,
        action: str,
        reason: str,
        planner_skipped: bool = False,
        deep_search: bool = False,
    ) -> None: ...

    def snapshot(self) -> "TurnMetricsSnapshot": ...

    def reset(self) -> None: ...
