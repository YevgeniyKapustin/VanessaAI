"""KnowledgeRetriever: intent-routed lookup over the vault indexes.

The bot never scans the whole vault: it consults per-folder ``_index.yaml``
manifests and resolves aliases/terms to files in O(1), then reads the matched
notes. Which parts are queried is driven by the turn intent:

- ``people`` — resolve nicknames → participant dossiers;
- ``lore``   — glossary aliases + event titles (also always queried for humor);
- ``culture`` — recommendation entries by kind/status;
- ``logs``   — recent weekly/daily logs.

When an embedding provider and a knowledge vector store are configured,
:meth:`fetch_semantic` additionally ranks the vault notes by embedding
similarity to the composed query — this is the primary semantic search (the
vault's notes are already semantic summaries), with alias/token matching kept
as an exact-hit complement.
"""

from __future__ import annotations

from vanessa.config.settings import settings
from vanessa.core.messages import ContextMessage
from vanessa.core.protocols import (
    EmbeddingProviderProtocol,
    KnowledgeVectorStoreProtocol,
)
from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.index.index import KnowledgeIndex
from vanessa.knowledge.people.entities import resolve_mentioned_people
from vanessa.knowledge.retriever.retriever_blocks import RetrieverBlocksMixin
from vanessa.knowledge.retriever.retriever_fetch import RetrieverFetchMixin
from vanessa.knowledge.retriever.retriever_hits import RetrieverHitsMixin
from vanessa.knowledge.retriever.retriever_match import RetrieverMatchMixin
from vanessa.knowledge.retriever.retriever_semantic import RetrieverSemanticMixin
from vanessa.knowledge.store.vault import KnowledgeVault


class KnowledgeRetriever(
    RetrieverFetchMixin,
    RetrieverSemanticMixin,
    RetrieverHitsMixin,
    RetrieverBlocksMixin,
    RetrieverMatchMixin,
):
    def __init__(
        self,
        vault: KnowledgeVault,
        index: KnowledgeIndex | None = None,
        *,
        max_blocks: int = 3,
        people_max_blocks: int = 1,
        embeddings: EmbeddingProviderProtocol | None = None,
        vector_store: KnowledgeVectorStoreProtocol | None = None,
        vector_top_k: int | None = None,
        vector_min_score: float | None = None,
        people_raw_max_chars: int | None = None,
        people_chunks_enabled: bool | None = None,
        people_chunk_chars: int | None = None,
        people_chunk_overlap: int | None = None,
        people_detail_blocks: int | None = None,
    ) -> None:
        self._vault = vault
        self._index = index or KnowledgeIndex(vault)
        self._max_blocks = max_blocks
        self._people_max_blocks = people_max_blocks
        self._embeddings = embeddings
        self._vector_store = vector_store
        self._vector_top_k = (
            vector_top_k
            if vector_top_k is not None
            else settings.knowledge_vector_top_k
        )
        self._vector_min_score = (
            vector_min_score
            if vector_min_score is not None
            else settings.knowledge_vector_min_score
        )
        self._people_raw_max_chars = (
            people_raw_max_chars
            if people_raw_max_chars is not None
            else settings.knowledge_people_raw_max_chars
        )
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
        self._people_detail_blocks = (
            people_detail_blocks
            if people_detail_blocks is not None
            else settings.knowledge_people_detail_blocks
        )

    async def resolve_people(
        self,
        message: str,
        recent_messages: list[ContextMessage] | None = None,
        *,
        recent_window: int | None = None,
        sender_name: str = "",
    ) -> list[str]:
        """Deterministic People-card files mentioned in message + recent window.

        A cheap alias scan over the People index (no LLM). Used by the compose
        path to pick which dossiers to inject and to decide whether the
        deterministic resolver may force People retrieval.
        """
        if not self._vault.is_configured:
            return []
        people_index = await self._index.load_folder(PEOPLE)
        return resolve_mentioned_people(
            message,
            recent_messages,
            people_index,
            recent_window=(
                recent_window
                if recent_window is not None
                else settings.knowledge_participant_recent_window
            ),
            sender_name=sender_name,
        )
