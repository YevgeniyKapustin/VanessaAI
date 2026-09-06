from typing import NotRequired, Protocol, TypedDict

from vanessa.core.messages import ContextBlock


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
        *,
        skip_fts: bool = False,
        anchor_max: int | None = None,
        fts_query: str | None = None,
        semantic_queries: list[str] | None = None,
        window_before: int | None = None,
        window_after: int | None = None,
    ) -> list[ContextBlock]: ...
