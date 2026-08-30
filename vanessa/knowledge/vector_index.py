"""KnowledgeVectorIndexer: embed the semantic vault notes into Qdrant.

The vault (People dossiers, Lore events/glossary, Culture, Logs) is Vanessa's
already-semantic memory — summaries written and merged by the memory stage and
the periodic sweep. Raw chat messages embed poorly, so retrieval prefers these
semantic notes: each note becomes one vector in the dedicated ``knowledge``
Qdrant collection, keyed by its vault-relative path.

The index stays fresh without a full rebuild: after every vault write the
changed note is re-embedded in place (idempotent — the point id is derived from
the path). ``index_all()``/``scripts/reindex_knowledge_vectors.py`` rebuild the
whole collection from scratch.
"""

from __future__ import annotations

import logging
import time

from vanessa.config import settings
from vanessa.core.protocols import (
    EmbeddingProviderProtocol,
    KnowledgeVectorStoreProtocol,
)
from vanessa.knowledge.chunks import split_dossier_chunks
from vanessa.knowledge.vault import KnowledgeVault

logger = logging.getLogger(__name__)

# Top-level vault folders that carry semantic content -> retrieval kind.
# The compaction archive holds the same semantically-summarized facts and quotes
# (with explanations) that were trimmed out of the live cards — embedding it
# keeps that history RAG-searchable, while the People alias index still ignores
# it (no person-card pollution).
_SEMANTIC_FOLDERS: dict[str, str] = {
    "People": "people",
    "Lore": "lore",
    "Culture": "culture",
    "Logs": "logs",
    "_archive": "people",
}


def knowledge_kind_for_path(path: str) -> str | None:
    """Map a vault-relative note path to its semantic kind (people/lore/...)."""
    for folder, kind in _SEMANTIC_FOLDERS.items():
        if path == folder or path.startswith(folder + "/"):
            return kind
    return None


class KnowledgeVectorIndexer:
    def __init__(
        self,
        vault: KnowledgeVault,
        embeddings: EmbeddingProviderProtocol,
        vector_store: KnowledgeVectorStoreProtocol,
        *,
        max_chars: int | None = None,
        batch_size: int = 64,
        people_chunks_enabled: bool | None = None,
        people_chunk_chars: int | None = None,
        people_chunk_overlap: int | None = None,
    ) -> None:
        self._vault = vault
        self._embeddings = embeddings
        self._vector_store = vector_store
        self._max_chars = (
            max_chars
            if max_chars is not None
            else settings.rag_embed_max_chars
        )
        self._batch_size = max(1, batch_size)
        self._people_chunks_enabled = (
            settings.knowledge_people_chunks_enabled
            if people_chunks_enabled is None
            else people_chunks_enabled
        )
        self._people_chunk_chars = (
            people_chunk_chars
            if people_chunk_chars is not None
            else settings.knowledge_people_chunk_chars
        )
        self._people_chunk_overlap = (
            people_chunk_overlap
            if people_chunk_overlap is not None
            else settings.knowledge_people_chunk_overlap
        )

    def _embed_text(self, kind: str, title: str, body: str) -> str:
        prefix = f"[{kind}] {title}".strip() if title else f"[{kind}]"
        text = f"{prefix}\n{body}".strip()
        if self._max_chars and len(text) > self._max_chars:
            text = text[: self._max_chars]
        return text

    def _chunks_for(self, kind: str, title: str, body: str) -> list[tuple[int, str]]:
        """Return ``(chunk_index, embed_text)`` for a note.

        People dossiers are chunked when enabled so each block is embedded and
        ranked separately; every other kind (and People when disabled) keeps a
        single whole-note vector.
        """
        if kind == "people" and self._people_chunks_enabled:
            blocks = split_dossier_chunks(
                body or "",
                self._people_chunk_chars,
                self._people_chunk_overlap,
            )
            return [
                (index, self._embed_text(kind, title, block))
                for index, block in enumerate(blocks)
                if block.strip()
            ]
        text = self._embed_text(kind, title, body or "")
        return [(0, text)] if text.strip() else []

    async def _collect_notes(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        for folder, kind in _SEMANTIC_FOLDERS.items():
            notes = await self._vault.list_notes(folder, recursive=True)
            for note in notes:
                items.append((note.relative_path, kind))
        return items

    async def index_all(self) -> int:
        """Embed every semantic note; returns the number of points upserted."""
        if not self._vault.is_configured:
            return 0
        await self._vector_store.ensure_collection()
        items: list[tuple[str, str, str, list[tuple[int, str]]]] = []
        for rel, kind in await self._collect_notes():
            note = await self._vault.read_note(rel)
            if note is None:
                continue
            title = str(note.meta.get("id") or rel)
            chunks = self._chunks_for(kind, title, note.body or "")
            if not chunks:
                continue
            items.append((rel, kind, title, chunks))
        return await self._embed_and_upsert(items)

    async def index_note(self, path: str) -> bool:
        """Re-embed a single note (called after a vault write)."""
        if not self._vault.is_configured:
            return False
        note = await self._vault.read_note(path)
        if note is None:
            return False
        kind = knowledge_kind_for_path(path)
        if kind is None:
            return False
        title = str(note.meta.get("id") or path)
        chunks = self._chunks_for(kind, title, note.body or "")
        if not chunks:
            return False
        from vanessa.infrastructure.observability.metrics import record_knowledge_vector_sync

        started = time.perf_counter()
        await self._vector_store.ensure_collection()
        vectors = await self._embeddings.embed_batch(
            [text for _, text in chunks]
        )
        if len(chunks) == 1 and chunks[0][0] == 0:
            await self._vector_store.upsert_note(
                path,
                kind,
                title,
                vectors[0],
            )
        else:
            await self._vector_store.upsert_note_chunks(
                path,
                kind,
                title,
                chunks,
                vectors,
            )
        record_knowledge_vector_sync(time.perf_counter() - started)
        logger.info(
            "knowledge_vector_indexed path=%s kind=%s chunks=%s",
            path,
            kind,
            len(chunks),
        )
        return True

    async def _embed_and_upsert(
        self,
        items: list[tuple[str, str, str, list[tuple[int, str]]]],
    ) -> int:
        if not items:
            return 0
        total = 0
        for start in range(0, len(items), self._batch_size):
            batch = items[start : start + self._batch_size]
            flat_chunks: list[tuple[int, str]] = []
            flat_meta: list[tuple[str, str, str, int]] = []
            for path, kind, title, chunks in batch:
                for index, text in chunks:
                    flat_meta.append((path, kind, title, index))
                    flat_chunks.append((index, text))
            vectors = await self._embeddings.embed_batch(
                [text for _, text in flat_chunks]
            )

            # Group the embedded texts back by note; single-vector notes use the
            # whole-note upsert, chunked People dossiers use the chunk upsert.
            by_note: dict[tuple[str, str, str], list[tuple[int, list[float]]]] = {}
            for (path, kind, title, index), vector in zip(flat_meta, vectors):
                by_note.setdefault((path, kind, title), []).append((index, vector))

            for (path, kind, title), chunk_vectors in by_note.items():
                if len(chunk_vectors) == 1 and chunk_vectors[0][0] == 0:
                    await self._vector_store.upsert_note(
                        path,
                        kind,
                        title,
                        chunk_vectors[0][1],
                    )
                else:
                    await self._vector_store.upsert_note_chunks(
                        path,
                        kind,
                        title,
                        [(index, "") for index, _ in chunk_vectors],
                        [vector for _, vector in chunk_vectors],
                    )
                total += len(chunk_vectors)
        logger.info("knowledge_vector_index_all notes=%s", total)
        return total
