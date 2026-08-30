from __future__ import annotations

import logging

from services.agent.runtime.lifecycle import AsyncRuntime
from services.agent.runtime.tasks import TaskSet
from vanessa.config import settings
from vanessa.infrastructure.observability.alerting import create_alert_manager

logger = logging.getLogger(__name__)


class AlertRuntime(AsyncRuntime):
    def __init__(self) -> None:
        self._tasks = TaskSet()

    async def start(self) -> None:
        alert_manager = create_alert_manager()
        if alert_manager is None:
            return
        self._tasks.spawn(
            alert_manager.run_forever(),
            name="alert_manager",
        )
        logger.info(
            "AlertManager started (chat_id=%s)",
            settings.alerting_dev_chat_id,
        )

    async def stop(self) -> None:
        await self._tasks.cancel_all()
