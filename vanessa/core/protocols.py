from datetime import datetime
from typing import Any, NotRequired, Protocol, TypedDict

from vanessa.config.content import MemeDefContent
from vanessa.core.knowledge_dto import KnowledgeBlock
from vanessa.core.messages import (
    ContextBlock,
    ContextMessage,
    ImageAttachment,
    PhotoCandidate,
    StoredMessage,
    WebResult,
)
from vanessa.core.turn import ChatTurnInput, ConversationTurnResult
from vanessa.core.turn_metrics import TurnMetricsSnapshot


class VectorSearchHit(TypedDict):
    message_id: int
    score: float


class KnowledgeVectorHit(TypedDict):
    path: str
    kind: str
    title: str
    score: float
    # Present when the hit is a chunk of a People dossier (chunked retrieval).
    # Absent for whole-note hits. The chunk text itself is re-read from the
    # vault by path + chunk_index at retrieval time.
    chunk_index: NotRequired[int]


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
        reply_to_message_id: int | None = None,
        reply_to_text: str | None = None,
        reply_to_sender_telegram_id: int | None = None,
        reply_to_sender_name: str | None = None,
        attachments: list[dict] | None = None,
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

    async def get_newer_than(
        self,
        after_message_id: int,
        limit: int = 200,
    ) -> list[StoredMessage]: ...

    async def get_messages_since(
        self,
        days: int,
        limit: int = 5000,
    ) -> list[StoredMessage]: ...

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

    async def update_photo_caption(
        self,
        message_id: int,
        caption: str,
    ) -> None: ...

    async def search_photo_messages(
        self,
        query: str,
        limit: int = 30,
    ) -> list[StoredMessage]: ...


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


class KnowledgeVectorStoreProtocol(Protocol):
    """Vector store for the semantic knowledge vault notes (People/Lore/...).

    Points are keyed by the note's vault-relative path, so re-embedding a note
    overwrites its vector in place (idempotent reindex).
    """

    async def ensure_collection(self) -> None: ...

    async def upsert_note(
        self,
        path: str,
        kind: str,
        title: str,
        vector: list[float],
    ) -> str: ...

    async def upsert_notes(
        self,
        items: list[tuple[str, str, str, list[float]]],
    ) -> list[str]: ...

    async def upsert_note_chunks(
        self,
        path: str,
        kind: str,
        title: str,
        chunks: list[tuple[int, str]],
        vectors: list[list[float]],
    ) -> list[str]: ...

    async def search(
        self,
        vector: list[float],
        limit: int = 30,
    ) -> list[KnowledgeVectorHit]: ...


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
    async def generate(
        self,
        user_message: str,
        context_blocks: list[ContextBlock],
        session_messages: list[ContextMessage] | None = None,
        humor_quotes: list[str] | None = None,
        knowledge_blocks: list[KnowledgeBlock] | None = None,
        web_blocks: list[WebResult] | None = None,
        meme_blocks: list[MemeDefContent] | None = None,
        meme_menu: list[MemeDefContent] | None = None,
        metrics_block: str | None = None,
        attitude_note: str | None = None,
        *,
        sender_telegram_id: int | None = None,
        sender_name: str | None = None,
        system_prompt: str | None = None,
        tone: str | None = None,
        needs_clarification: bool = False,
        clarification_hint: str = "",
        detail: str = "normal",
        uses_pro_model: bool = False,
        reply_to_text: str | None = None,
        reply_to_sender_telegram_id: int | None = None,
        reply_to_sender_name: str | None = None,
        images: list[ImageAttachment] | None = None,
        photo_candidates: list[PhotoCandidate] | None = None,
        current_images: list[ImageAttachment] | None = None,
    ) -> str: ...


class PhotoCaptionerProtocol(Protocol):
    """Generates a short one-line description of a photo (RAG enrichment)."""

    async def generate(self, attachment: ImageAttachment) -> str | None: ...


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

    def snapshot(self) -> TurnMetricsSnapshot: ...

    def reset(self) -> None: ...
