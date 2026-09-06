"""Producer-side task dispatch: agent publishes work for the worker."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from vanessa.contracts.messages import TaskKind, TaskMessage

logger = logging.getLogger(__name__)


class TaskDispatcher(Protocol):
    """Schedules a background task (sync, fire-and-forget)."""

    def submit(
        self,
        task: TaskKind,
        payload: dict,
        *,
        dedup_key: str | None = None,
    ) -> None: ...


class BrokerTaskDispatcher:
    """Publishes tasks to the worker's stream as ``TaskMessage``s."""

    def __init__(self, broker, tasks_stream: str) -> None:
        self._broker = broker
        self._tasks_stream = tasks_stream
        self._pending: set[asyncio.Task] = set()

    def submit(self, task, payload, *, dedup_key=None) -> None:
        message = TaskMessage(task=task, payload=payload, dedup_key=dedup_key)
        task_handle = asyncio.create_task(
            self._broker.publish(self._tasks_stream, message)
        )
        self._pending.add(task_handle)
        task_handle.add_done_callback(self._pending.discard)


class NoopTaskDispatcher:
    """Drops tasks (used when background work is fully disabled)."""

    def submit(self, task, payload, *, dedup_key=None) -> None:
        del payload, dedup_key
        logger.debug("task_dropped task=%s", task)
