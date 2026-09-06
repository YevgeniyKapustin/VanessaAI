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

from vanessa.config import settings
from vanessa.core.protocols import (
    EmbeddingProviderProtocol,
    KnowledgeVectorStoreProtocol,
)
from vanessa.knowledge.store.vault import KnowledgeVault
from vanessa.knowledge.vectors.chunks import split_dossier_chunks
from vanessa.knowledge.vectors.vector_index_ops import (
    index_all_notes,
    index_one_note,
)
from vanessa.knowledge.vectors.vector_kinds import (
    SEMANTIC_FOLDERS,
    knowledge_kind_for_path,
)

__all__ = ["KnowledgeVectorIndexer", "knowledge_kind_for_path"]


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
        for folder, kind in SEMANTIC_FOLDERS.items():
            notes = await self._vault.list_notes(folder, recursive=True)
            for note in notes:
                items.append((note.relative_path, kind))
        return items

    async def index_all(self) -> int:
        """Embed every semantic note; returns the number of points upserted."""
        return await index_all_notes(self)

    async def index_note(self, path: str) -> bool:
        """Re-embed a single note (called after a vault write)."""
        return await index_one_note(self, path)
