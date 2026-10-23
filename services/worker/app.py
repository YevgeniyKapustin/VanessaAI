"""Worker app: consumes task messages and runs the matching handler."""

from __future__ import annotations

import asyncio
import logging

from vanessa.contracts.messages import TaskMessage
from vanessa.infrastructure.broker.backends import Delivery

logger = logging.getLogger(__name__)


class WorkerApp:
    """Consumes ``TaskMessage``s from the broker and dispatches to handlers.

    Optionally also runs the polling sweep/portrait loops, so the whole
    background workload lives in this one isolated process.
    """

    def __init__(
        self,
        broker,
        handlers: dict,
        *,
        tasks_stream: str,
        group: str,
        consumer: str,
        dedup=None,
        sweep_worker=None,
        portrait_worker=None,
        scheduler=None,
    ) -> None:
        self._broker = broker
        self._handlers = dict(handlers)
        self._tasks_stream = tasks_stream
        self._group = group
        self._consumer = consumer
        self._dedup = dedup
        # Polling loops next to the task consumer; None skips one.
        self._loops = [
            loop
            for loop in (sweep_worker, portrait_worker, scheduler)
            if loop is not None
        ]

    async def run_forever(self) -> None:
        tasks = [asyncio.create_task(self._consume_tasks())]
        tasks.extend(asyncio.create_task(loop.run_forever()) for loop in self._loops)
        await asyncio.gather(*tasks)

    async def _consume_tasks(self) -> None:
        await self._broker.consume_forever(
            self._tasks_stream,
            self._group,
            self._consumer,
            self._handle,
            dedup=self._dedup,
        )

    async def _handle(self, delivery: Delivery) -> None:
        message = delivery.message
        if not isinstance(message, TaskMessage):
            logger.warning(
                "worker_unexpected kind=%s stream=%s", message.message_kind(), delivery.stream
            )
            return
        handler = self._handlers.get(message.task)
        if handler is None:
            logger.warning("worker_no_handler task=%s", message.task)
            return
        # Let failures propagate → the consume loop moves the message to the DLQ.
        await handler.handle(message)
