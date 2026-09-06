"""Batch embed + upsert for knowledge vector indexing."""

from __future__ import annotations

import logging

from vanessa.core.protocols import (
    EmbeddingProviderProtocol,
    KnowledgeVectorStoreProtocol,
)

logger = logging.getLogger(__name__)


def _flatten_batch(
    batch: list[tuple[str, str, str, list[tuple[int, str]]]],
) -> tuple[list[tuple[str, str, str, int]], list[tuple[int, str]]]:
    flat_chunks: list[tuple[int, str]] = []
    flat_meta: list[tuple[str, str, str, int]] = []
    for path, kind, title, chunks in batch:
        for index, text in chunks:
            flat_meta.append((path, kind, title, index))
            flat_chunks.append((index, text))
    return flat_meta, flat_chunks


def _group_by_note(
    flat_meta: list[tuple[str, str, str, int]],
    vectors: list,
) -> dict[tuple[str, str, str], list[tuple[int, list[float]]]]:
    by_note: dict[tuple[str, str, str], list[tuple[int, list[float]]]] = {}
    for (path, kind, title, index), vector in zip(
        flat_meta, vectors, strict=False
    ):
        by_note.setdefault((path, kind, title), []).append((index, vector))
    return by_note


async def _upsert_one_note(
    vector_store: KnowledgeVectorStoreProtocol,
    path: str,
    kind: str,
    title: str,
    chunk_vectors: list[tuple[int, list[float]]],
) -> int:
    if len(chunk_vectors) == 1 and chunk_vectors[0][0] == 0:
        await vector_store.upsert_note(
            path,
            kind,
            title,
            chunk_vectors[0][1],
        )
    else:
        await vector_store.upsert_note_chunks(
            path,
            kind,
            title,
            [(index, "") for index, _ in chunk_vectors],
            [vector for _, vector in chunk_vectors],
        )
    return len(chunk_vectors)


async def _upsert_grouped(
    vector_store: KnowledgeVectorStoreProtocol,
    by_note: dict[tuple[str, str, str], list[tuple[int, list[float]]]],
) -> int:
    total = 0
    for (path, kind, title), chunk_vectors in by_note.items():
        total += await _upsert_one_note(
            vector_store, path, kind, title, chunk_vectors
        )
    return total


async def embed_and_upsert(
    embeddings: EmbeddingProviderProtocol,
    vector_store: KnowledgeVectorStoreProtocol,
    items: list[tuple[str, str, str, list[tuple[int, str]]]],
    batch_size: int,
) -> int:
    if not items:
        return 0
    total = 0
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        flat_meta, flat_chunks = _flatten_batch(batch)
        vectors = await embeddings.embed_batch(
            [text for _, text in flat_chunks]
        )
        by_note = _group_by_note(flat_meta, vectors)
        total += await _upsert_grouped(vector_store, by_note)
    logger.info("knowledge_vector_index_all notes=%s", total)
    return total
