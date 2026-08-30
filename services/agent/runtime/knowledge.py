from __future__ import annotations

import logging

from services.agent.container.app import AppContainer
from services.agent.runtime.lifecycle import AsyncRuntime
from services.agent.runtime.tasks import TaskSet
from vanessa.config import settings

logger = logging.getLogger(__name__)


class KnowledgeRuntime(AsyncRuntime):
    def __init__(self, container: AppContainer) -> None:
        self._container = container
        self._tasks = TaskSet()

    async def start(self) -> None:
        knowledge = self._container.graph.knowledge
        await knowledge.vault.ensure_structure()
        if not self._container.role.owns_knowledge_loops:
            return
        try:
            from vanessa.knowledge.compaction import compact_all_person_cards

            await compact_all_person_cards(knowledge.vault)
        except Exception:
            logger.exception("knowledge_compaction_failed at startup")
        if settings.knowledge_sweep_enabled:
            self._tasks.spawn(
                knowledge.sweep_worker().run_forever(),
                name="knowledge_sweep",
            )
        if settings.knowledge_portrait_enabled:
            self._tasks.spawn(
                knowledge.portrait_worker().run_forever(),
                name="knowledge_portrait",
            )
        self._tasks.spawn(
            self._index_vault(knowledge.vector_indexer),
            name="vault_index",
        )

    async def stop(self) -> None:
        await self._tasks.cancel_all()

    async def _index_vault(self, indexer) -> None:
        try:
            await indexer.index_all()
        except Exception:
            logger.exception("knowledge_vector_index_all_failed at startup")
