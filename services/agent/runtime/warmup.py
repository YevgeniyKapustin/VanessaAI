from __future__ import annotations

import asyncio

from services.agent.container.app import AppContainer
from services.agent.runtime.lifecycle import AsyncRuntime
from vanessa.pipeline.rag.embeddings.local_embeddings import preload_embedding_model


class WarmupRuntime(AsyncRuntime):
    def __init__(self, container: AppContainer) -> None:
        self._container = container

    async def start(self) -> None:
        retrieval = self._container.graph.retrieval
        await retrieval.indexes.messages.ensure_collection()
        await asyncio.to_thread(preload_embedding_model)
        await retrieval.embeddings.embed("warmup")

    async def stop(self) -> None:
        return None
