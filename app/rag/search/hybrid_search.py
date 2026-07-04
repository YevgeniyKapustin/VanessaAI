import logging
import time

from app.config import settings
from app.config.content import get_content
from app.core.messages import ContextBlock, RAG_SOURCE_ROLE, stored_block_to_context
from app.core.protocols import (
    ContextRetrieverProtocol,
    EmbeddingProviderProtocol,
    MessageIndexerProtocol,
    MessageRepositoryProtocol,
    TurnQueryProtocol,
    VectorStoreProtocol,
)
from app.rag.search.merger import merge_hybrid_results, merge_vector_search_hits

logger = logging.getLogger(__name__)


def effective_window_max_total(anchor_max: int | None = None) -> int:
    anchors = anchor_max or settings.rag_anchor_max
    per_window = (
        settings.rag_context_window_before
        + 1
        + settings.rag_context_window_after
    )
    return max(settings.rag_context_window_max_total, anchors * per_window)


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

        embed_texts: list[str] = []
        if semantic_queries:
            seen: set[str] = set()
            for text in semantic_queries:
                normalized = text.strip()
                if not normalized:
                    continue
                key = normalized.lower()
                if key in seen:
                    continue
                seen.add(key)
                embed_texts.append(normalized)

        vectors: list[list[float]] = []
        if query_vector is not None:
            vectors.append(query_vector)
        if embed_texts:
            vectors.extend(await self._embeddings.embed_batch(embed_texts))
        if not vectors:
            vectors.append(await self._embeddings.embed(query))

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

        fts_hits: list = []
        fts_ms = 0.0
        if not skip_fts:
            fts_started = time.perf_counter()
            fts_hits = await self._messages.fulltext_search(
                query=fts_query or query,
                limit=top_k,
            )
            fts_ms = (time.perf_counter() - fts_started) * 1000

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
            return []

        before = window_before if window_before is not None else settings.rag_context_window_before
        after = window_after if window_after is not None else settings.rag_context_window_after
        max_total = effective_window_max_total(anchor_max)
        window_started = time.perf_counter()
        if before > 0 or after > 0:
            raw_blocks = await self._messages.get_conversation_window_blocks(
                anchor_ids=selected_ids,
                before=before,
                after=after,
                max_total=max_total,
            )
            blocks = [
                block
                for anchor_id, messages in raw_blocks
                if (block := stored_block_to_context(anchor_id, messages)) is not None
            ]
            message_count = sum(len(block.messages) for block in blocks)
            window_ms = (time.perf_counter() - window_started) * 1000
            logger.info(
                "rag_context_expanded query=%r anchors=%s blocks=%s messages=%s "
                "vector_ms=%.1f fts_ms=%.1f window_ms=%.1f",
                query,
                len(selected_ids),
                len(blocks),
                message_count,
                vector_ms,
                fts_ms,
                window_ms,
            )
            return blocks

        messages = await self._messages.get_by_ids(selected_ids)
        user_messages = [message for message in messages if message.role == RAG_SOURCE_ROLE]
        window_ms = (time.perf_counter() - window_started) * 1000
        logger.info(
            "rag_search_done query=%r anchors=%s vector_ms=%.1f fts_ms=%.1f "
            "window_ms=%.1f",
            query,
            len(user_messages),
            vector_ms,
            fts_ms,
            window_ms,
        )
        return [
            block
            for message in user_messages
            if (block := stored_block_to_context(message.id, [message])) is not None
        ]

    async def _user_anchor_ids(self, message_ids: list[int]) -> list[int]:
        if not message_ids:
            return []
        messages = await self._messages.get_by_ids(message_ids)
        roles = {message.id: message.role for message in messages}
        return [mid for mid in message_ids if roles.get(mid) == RAG_SOURCE_ROLE]
