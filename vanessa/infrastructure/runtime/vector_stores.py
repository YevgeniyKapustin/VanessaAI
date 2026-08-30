"""Shared embedding + Qdrant stores for agent-core and worker.

Neither process should import the other's container to get these.
"""

from __future__ import annotations

from vanessa.pipeline.rag.embeddings.embeddings import LocalEmbeddingProvider
from vanessa.pipeline.rag.qdrant_client import KnowledgeQdrantStore, QdrantVectorStore


def create_embedding_provider() -> LocalEmbeddingProvider:
    return LocalEmbeddingProvider()


def create_message_vector_store() -> QdrantVectorStore:
    return QdrantVectorStore()


def create_knowledge_vector_store() -> KnowledgeQdrantStore:
    return KnowledgeQdrantStore()
