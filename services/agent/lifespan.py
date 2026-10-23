from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from services.agent.container import AppContainer
from services.agent.runtime.alerts import AlertRuntime
from services.agent.runtime.broker import BrokerRuntime
from services.agent.runtime.jobs import JobsRuntime
from services.agent.runtime.knowledge import KnowledgeRuntime
from services.agent.runtime.storage import StorageRuntime


@asynccontextmanager
async def lifespan(container: AppContainer) -> AsyncIterator[None]:
    runtimes = (
        StorageRuntime(),
        JobsRuntime(container),
        AlertRuntime(),
        KnowledgeRuntime(container),
        BrokerRuntime(container),
    )

    async with AsyncExitStack() as stack:
        for runtime in runtimes:
            await stack.enter_async_context(runtime)
        yield
