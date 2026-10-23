"""Knowledge-pipeline task handlers: sweep, portraits, memory, metrics."""

from __future__ import annotations

import logging

from vanessa.contracts.messages import TaskMessage
from vanessa.core.messages import context_message_from_payload
from vanessa.infrastructure.db import repository

logger = logging.getLogger(__name__)


class SweepHandler:
    """Run one knowledge-sweep cycle (messages newer than the cursor)."""

    def __init__(self, sweep, session_factory) -> None:
        self._sweep = sweep
        self._session_factory = session_factory

    async def handle(self, _task: TaskMessage) -> None:
        async with self._session_factory() as session:
            processed = await self._sweep.run(repository.MessageRepository(session))
            logger.info("worker_sweep processed=%s", processed)


class PortraitHandler:
    """Regenerate stale person portraits."""

    def __init__(self, builder) -> None:
        self._builder = builder

    async def handle(self, _task: TaskMessage) -> None:
        updated = await self._builder.run()
        logger.info("worker_portrait updated=%s", updated)


class MemoryExtractHandler:
    def __init__(self, memory) -> None:
        self._memory = memory

    async def handle(self, task: TaskMessage) -> None:
        payload = task.payload
        raw_messages = payload.get("messages") or []
        recent = [
            context_message_from_payload(item)
            for item in raw_messages
            if isinstance(item, dict)
        ]
        source_ids = [int(value) for value in (payload.get("source_message_ids") or [])]
        chat_id = payload.get("telegram_chat_id")
        await self._memory.run(
            recent_messages=recent,
            source_message_ids=source_ids or None,
            telegram_chat_id=int(chat_id) if chat_id is not None else None,
        )


class MetricsSnapshotHandler:
    def __init__(self, metrics, session_factory) -> None:
        self._metrics = metrics
        self._session_factory = session_factory

    async def handle(self, task: TaskMessage) -> None:
        sender = task.payload.get("sender_telegram_id")
        only = {int(sender)} if sender is not None else None
        async with self._session_factory() as session:
            await self._metrics.run(
                repository.MessageRepository(session),
                semantic=False,
                only_senders=only,
            )
