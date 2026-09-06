"""Index-all / index-note payloads for KnowledgeVectorIndexer."""

from __future__ import annotations

import logging
import time

from vanessa.infrastructure.observability.metrics import (
    record_knowledge_vector_sync,
)
from vanessa.knowledge.vectors.vector_index_batch import embed_and_upsert
from vanessa.knowledge.vectors.vector_kinds import knowledge_kind_for_path

logger = logging.getLogger("vanessa.knowledge.vectors.vector_index")


def title_and_chunks(indexer, note, path: str, kind: str):
    title = str(note.meta.get("id") or path)
    chunks = indexer._chunks_for(kind, title, note.body or "")
    if not chunks:
        return None
    return title, chunks


async def note_payload_for_kind(indexer, path: str, kind: str):
    note = await indexer._vault.read_note(path)
    if note is None:
        return None
    prepared = title_and_chunks(indexer, note, path, kind)
    if prepared is None:
        return None
    title, chunks = prepared
    return (path, kind, title, chunks)


async def collect_index_payloads(indexer) -> list:
    items = []
    for rel, kind in await indexer._collect_notes():
        item = await note_payload_for_kind(indexer, rel, kind)
        if item is None:
            continue
        items.append(item)
    return items


async def index_all_notes(indexer) -> int:
    if not indexer._vault.is_configured:
        return 0
    await indexer._vector_store.ensure_collection()
    items = await collect_index_payloads(indexer)
    return await embed_and_upsert(
        indexer._embeddings, indexer._vector_store, items, indexer._batch_size
    )


async def prepare_index_note(indexer, path: str):
    note = await indexer._vault.read_note(path)
    if note is None:
        return None
    kind = knowledge_kind_for_path(path)
    if kind is None:
        return None
    prepared = title_and_chunks(indexer, note, path, kind)
    if prepared is None:
        return None
    title, chunks = prepared
    return kind, title, chunks


async def upsert_note_vectors(indexer, path, kind, title, chunks, vectors) -> None:
    if len(chunks) == 1 and chunks[0][0] == 0:
        await indexer._vector_store.upsert_note(path, kind, title, vectors[0])
        return
    await indexer._vector_store.upsert_note_chunks(
        path, kind, title, chunks, vectors
    )


async def index_one_note(indexer, path: str) -> bool:
    if not indexer._vault.is_configured:
        return False
    prepared = await prepare_index_note(indexer, path)
    if prepared is None:
        return False
    kind, title, chunks = prepared
    started = time.perf_counter()
    await indexer._vector_store.ensure_collection()
    vectors = await indexer._embeddings.embed_batch(
        [text for _, text in chunks]
    )
    await upsert_note_vectors(indexer, path, kind, title, chunks, vectors)
    record_knowledge_vector_sync(time.perf_counter() - started)
    logger.info(
        "knowledge_vector_indexed path=%s kind=%s chunks=%s",
        path,
        kind,
        len(chunks),
    )
    return True
