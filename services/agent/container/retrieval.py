from __future__ import annotations

from vanessa.core.protocols import (
    EmbeddingProviderProtocol,
    KnowledgeVectorStoreProtocol,
    VectorStoreProtocol,
)
from vanessa.infrastructure.runtime.vector_stores import (
    create_embedding_provider,
    create_knowledge_vector_store,
    create_message_vector_store,
)


class VectorIndexes:
    def __init__(
        self,
        messages: VectorStoreProtocol | None = None,
        knowledge: KnowledgeVectorStoreProtocol | None = None,
    ) -> None:
        self.messages = messages or create_message_vector_store()
        self.knowledge = knowledge or create_knowledge_vector_store()


class RetrievalStack:
    def __init__(
        self,
        embeddings: EmbeddingProviderProtocol | None = None,
        indexes: VectorIndexes | None = None,
    ) -> None:
        self.embeddings = embeddings or create_embedding_provider()
        self.indexes = indexes or VectorIndexes()
