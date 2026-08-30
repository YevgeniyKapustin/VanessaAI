from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from services.agent.runtime.alerts import AlertRuntime
from services.agent.runtime.broker import BrokerRuntime
from services.agent.runtime.jobs import JobsRuntime
from services.agent.runtime.knowledge import KnowledgeRuntime
from services.agent.runtime.storage import StorageRuntime
from services.agent.runtime.warmup import WarmupRuntime


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = app.state.container
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(StorageRuntime())
        await stack.enter_async_context(WarmupRuntime(container))
        await stack.enter_async_context(JobsRuntime(container))
        await stack.enter_async_context(AlertRuntime())
        await stack.enter_async_context(KnowledgeRuntime(container))
        await stack.enter_async_context(BrokerRuntime(container))
        yield
