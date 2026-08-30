from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from services.agent.container import AppContainer
from services.agent.runtime.alerts import AlertRuntime
from services.agent.runtime.broker import BrokerRuntime
from services.agent.runtime.jobs import JobsRuntime
from services.agent.runtime.knowledge import KnowledgeRuntime
from services.agent.runtime.storage import StorageRuntime
from services.agent.runtime.warmup import WarmupRuntime


@asynccontextmanager
async def lifespan(container: AppContainer) -> AsyncIterator[None]:
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(StorageRuntime())
        await stack.enter_async_context(WarmupRuntime(container))
        await stack.enter_async_context(JobsRuntime(container))
        await stack.enter_async_context(AlertRuntime())
        await stack.enter_async_context(KnowledgeRuntime(container))
        await stack.enter_async_context(BrokerRuntime(container))
        yield
