from __future__ import annotations

import logging

from services.agent.container.app import AppContainer
from services.agent.runtime.lifecycle import AsyncRuntime
from services.agent.runtime.tasks import TaskSet
from vanessa.config import settings
from vanessa.knowledge.memory import compaction

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
        await self._compact_person_cards(knowledge.vault)
        self._spawn_knowledge_workers(knowledge)

    async def _compact_person_cards(self, vault) -> None:
        try:
            await compaction.compact_all_person_cards(vault)
        except Exception:
            logger.exception("knowledge_compaction_failed at startup")

    def _spawn_knowledge_workers(self, knowledge) -> None:
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

    async def stop(self) -> None:
        await self._tasks.cancel_all()
