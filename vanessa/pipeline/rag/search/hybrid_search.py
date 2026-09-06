import logging
import time

from vanessa.config import settings
from vanessa.config.content import get_content
from vanessa.core.messages import RAG_SOURCE_ROLE, ContextBlock
from vanessa.core.protocols import (
    ContextRetrieverProtocol,
    EmbeddingProviderProtocol,
    MessageIndexerProtocol,
    MessageRepositoryProtocol,
    TurnQueryProtocol,
    VectorStoreProtocol,
)
from vanessa.infrastructure.observability.metrics import record_rag_search
from vanessa.pipeline.rag.search.hybrid_vectors import resolve_search_vectors
from vanessa.pipeline.rag.search.hybrid_windows import (
    effective_window_max_total,
    load_selected_context_blocks,
)
from vanessa.pipeline.rag.search.merger import (
    merge_hybrid_results,
    merge_vector_search_hits,
)

logger = logging.getLogger(__name__)

__all__ = ["HybridSearchService", "effective_window_max_total"]


class HybridSearchService(
    TurnQueryProtocol,
    ContextRetrieverProtocol,
    MessageIndexerProtocol,
):
    def __init__(
        self,
        message_repo: MessageRepositoryProtocol,
        embedding_provider: EmbeddingProviderProtocol,
        vector_store: VectorStoreProtocol,
    ) -> None:
        self._messages = message_repo
        self._embeddings = embedding_provider
        self._vector_store = vector_store

    async def embed_query(self, query: str) -> list[float]:
        return await self._embeddings.embed(query)

    async def index(
        self,
        message_id: int,
        role: str,
        content: str,
        point_id: str | None = None,
    ) -> str:
        if role != RAG_SOURCE_ROLE:
            return point_id or ""
        vector = await self._embeddings.embed(content)
        return await self._vector_store.upsert_message(
            message_id=message_id,
            role=role,
            content=content,
            vector=vector,
            point_id=point_id,
        )

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
    ) -> list[ContextBlock]:
        if not query.strip() and not (semantic_queries or query_vector):
            return []

        top_k = top_k or settings.rag_hybrid_top_k
        min_score = get_content().rag.vector_min_score or settings.rag_vector_min_score
        vectors = await resolve_search_vectors(
            self._embeddings, query, query_vector, semantic_queries
        )

        started = time.perf_counter()
        vector_hit_lists = [
            await self._vector_store.search(vector=vector, limit=top_k)
            for vector in vectors
        ]
        vector_hits = merge_vector_search_hits(vector_hit_lists)
        vector_ms = (time.perf_counter() - started) * 1000
        top_score = float(vector_hits[0]["score"]) if vector_hits else 0.0
        vector_hits = [
            hit for hit in vector_hits if float(hit["score"]) >= min_score
        ]

        fts_hits, fts_ms = await self._fts_hits(
            query, top_k, skip_fts=skip_fts, fts_query=fts_query
        )
        selected_ids = merge_hybrid_results(
            vector_hits,
            fts_hits,
            context_min=min(
                settings.rag_context_min,
                anchor_max or settings.rag_anchor_max,
            ),
            context_max=anchor_max or settings.rag_anchor_max,
        )
        selected_ids = await self._user_anchor_ids(selected_ids)
        if not selected_ids:
            logger.info(
                "rag_search_empty query=%r vector_hits=%s fts_hits=%s "
                "top_score=%.3f min_score=%.3f vector_ms=%.1f fts_ms=%.1f",
                query,
                len(vector_hits),
                len(fts_hits),
                top_score,
                min_score,
                vector_ms,
                fts_ms,
            )
            record_rag_search("raw", hits=0, top_score=top_score)
            return []

        return await load_selected_context_blocks(
            self._messages,
            query,
            selected_ids,
            window_before=window_before,
            window_after=window_after,
            anchor_max=anchor_max,
            vector_ms=vector_ms,
            fts_ms=fts_ms,
            top_score=top_score,
        )

    async def _fts_hits(
        self,
        query: str,
        top_k: int,
        *,
        skip_fts: bool,
        fts_query: str | None,
    ) -> tuple[list, float]:
        if skip_fts:
            return [], 0.0
        fts_started = time.perf_counter()
        fts_hits = await self._messages.fulltext_search(
            query=fts_query or query,
            limit=top_k,
        )
        return fts_hits, (time.perf_counter() - fts_started) * 1000

    async def _user_anchor_ids(self, message_ids: list[int]) -> list[int]:
        if not message_ids:
            return []
        messages = await self._messages.get_by_ids(message_ids)
        roles = {message.id: message.role for message in messages}
        return [mid for mid in message_ids if roles.get(mid) == RAG_SOURCE_ROLE]
