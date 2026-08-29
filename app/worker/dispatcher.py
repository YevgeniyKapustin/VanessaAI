"""Producer-side task dispatch: how the agent core hands work to the worker.

``BrokerTaskDispatcher`` publishes ``TaskMessage``s to the worker's stream;
the worker consumer acks after success and moves failures to the DLQ, so
at-least-once delivery is guaranteed on the consumer side.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from app.contracts.messages import TaskKind

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

    def submit(self, task, payload, *, dedup_key=None) -> None:
        from app.contracts.messages import TaskMessage

        message = TaskMessage(task=task, payload=payload, dedup_key=dedup_key)
        # Publishing is async; the reply path must never await it. The bounded
        # broker stream + consumer DLQ handle backpressure and redelivery.
        asyncio.create_task(self._broker.publish(self._tasks_stream, message))


class NoopTaskDispatcher:
    """Drops tasks (used when background work is fully disabled)."""

    def submit(self, task, payload, *, dedup_key=None) -> None:
        logger.debug("task_dropped task=%s", task)
