#!/usr/bin/env python
"""Rebuild the semantic knowledge vector index in Qdrant.

Usage:
    python scripts/reindex_knowledge_vectors.py

Drops and recreates the ``knowledge`` collection, then embeds every semantic
vault note (People/Lore/Culture/Logs) into it. Run after bulk manual edits to
the vault (merging/renaming cards), or to seed the collection for the first
time.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from vanessa.config.settings import settings
from vanessa.knowledge.vault import KnowledgeVault
from vanessa.knowledge.vector_index import KnowledgeVectorIndexer
from vanessa.rag.embeddings.local_embeddings import LocalEmbeddingProvider
from vanessa.rag.qdrant_client import KnowledgeQdrantStore


async def main() -> int:
    vault = KnowledgeVault()
    if not vault.is_configured:
        print("Knowledge vault is not configured (KNOWLEDGE_PATH empty)")
        return 1
    if not settings.qdrant_knowledge_collection:
        print("Qdrant knowledge collection is not configured")
        return 1

    store = KnowledgeQdrantStore()
    embeddings = LocalEmbeddingProvider()
    indexer = KnowledgeVectorIndexer(vault, embeddings, store)

    print(
        f"resetting collection '{settings.qdrant_knowledge_collection}'..."
    )
    await store.reset()
    count = await indexer.index_all()
    print(f"indexed {count} semantic notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
