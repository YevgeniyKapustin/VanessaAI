from __future__ import annotations

import logging

from services.agent.runtime.lifecycle import AsyncRuntime
from vanessa.config import settings
from vanessa.infrastructure.db.base import Base
from vanessa.infrastructure.db.session import engine

logger = logging.getLogger(__name__)


class StorageRuntime(AsyncRuntime):
    async def start(self) -> None:
        if not settings.api_auto_create_schema:
            return
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.warning("API_AUTO_CREATE_SCHEMA enabled: used create_all")

    async def stop(self) -> None:
        await engine.dispose()
