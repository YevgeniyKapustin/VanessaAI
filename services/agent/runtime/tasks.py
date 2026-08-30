from __future__ import annotations

import asyncio
import contextlib
import logging

logger = logging.getLogger(__name__)


class TaskSet:
    def __init__(self) -> None:
        self._items: list[tuple[asyncio.Task, str, bool]] = []

    def spawn(self, coro, *, name: str, log_stop: bool = False) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._items.append((task, name, log_stop))
        return task

    async def cancel_all(self) -> None:
        for task, name, log_stop in self._items:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            if log_stop:
                logger.info("%s stopped", name)
        self._items.clear()
