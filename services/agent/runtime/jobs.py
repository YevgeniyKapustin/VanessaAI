from __future__ import annotations

from services.agent.container.app import AppContainer
from services.agent.runtime.lifecycle import AsyncRuntime


class JobsRuntime(AsyncRuntime):
    def __init__(self, container: AppContainer) -> None:
        self._container = container

    async def start(self) -> None:
        self._container.graph.jobs.start()

    async def stop(self) -> None:
        await self._container.graph.jobs.shutdown()
