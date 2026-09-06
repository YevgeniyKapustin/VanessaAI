"""Assemble KnowledgeBlocks from vector and FTS hits."""

from __future__ import annotations

import logging

from vanessa.infrastructure.observability.metrics import (
    record_knowledge_search,
    record_rag_search,
)
from vanessa.knowledge.retriever.retriever_hit_blocks import RetrieverHitBlocksMixin
from vanessa.knowledge.schema import KnowledgeBlock

logger = logging.getLogger("vanessa.knowledge.retriever")


class RetrieverHitsMixin(RetrieverHitBlocksMixin):
    async def _semantic_span(
        self,
        span,
        *,
        effective: str,
        indexes: set[str],
        knowledge_query: str,
        humor_ok: bool,
        humor_query: str,
        user_message: str,
        top_k: int | None,
        people_detail: bool,
        chunked_detail: bool,
        self_paths: set[str],
        target_files: list[str],
        has_non_self_target: bool,
    ) -> list[KnowledgeBlock]:
        assert self._embeddings is not None
        assert self._vector_store is not None
        query_vector = await self._embeddings.embed(effective)
        hits = await self._vector_store.search(
            query_vector,
            limit=top_k or self._vector_top_k,
        )
        record_knowledge_search("qdrant", hits=len(hits))
        span.update(
            output={
                "hits": [
                    {
                        "path": hit.get("path"),
                        "kind": hit.get("kind"),
                        "title": hit.get("title"),
                        "score": hit.get("score"),
                    }
                    for hit in hits[:12]
                ]
            }
        )
        fts_notes = await self._vault.search_fts(
            effective, limit=top_k or self._vector_top_k
        )
        record_knowledge_search("postgres_fts", hits=len(fts_notes))
        vector_blocks, seen_paths, people_chunk_hits = await self._blocks_from_hits(
            hits,
            indexes=indexes,
            people_detail=people_detail,
            chunked_detail=chunked_detail,
            self_paths=self_paths,
            has_non_self_target=has_non_self_target,
        )
        await self._append_people_chunks(
            vector_blocks, seen_paths, people_chunk_hits
        )
        await self._append_fts_blocks(
            vector_blocks, seen_paths, fts_notes, indexes, people_detail=people_detail
        )
        alias_blocks = await self.fetch(
            knowledge_indexes=tuple(sorted(indexes)),
            knowledge_query=knowledge_query,
            humor_ok=humor_ok,
            humor_query=humor_query,
            user_message=user_message,
            people_detail=people_detail,
            people_files=target_files or None,
        )
        merged = self._dedupe(alias_blocks + vector_blocks)
        missing_targets = sorted(
            path
            for path in target_files
            if path not in self_paths
            and path not in seen_paths
            and path not in people_chunk_hits
        )
        if missing_targets:
            logger.warning(
                "knowledge_semantic_target_missing_from_vectors files=%s "
                "-> run scripts/reindex_knowledge_vectors.py",
                missing_targets,
            )
        logger.info(
            "knowledge_fetch_semantic query=%r vector_hits=%s blocks=%s "
            "indexes=%s people_chunks=%s",
            effective,
            len(hits),
            len(merged),
            sorted(indexes) or "all",
            len(people_chunk_hits),
        )
        top_score = float(hits[0]["score"]) if hits else None
        record_rag_search("semantic", hits=len(merged), top_score=top_score)
        return merged[: self._detail_cap(detail=people_detail)]
