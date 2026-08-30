"""Outbox relay: publishes staged outbox rows to the broker.

One relay worker per process polls pending ``OutboxEvent`` rows, publishes
each to its target stream, and marks it delivered. At-least-once by design: a
crash after publish but before ``mark_delivered`` leaves the row pending and
the consumer's dedup guard swallows the duplicate.
"""

from __future__ import annotations

import asyncio
import logging

from vanessa.infrastructure.broker.serialization import decode
from vanessa.infrastructure.outbox.repository import OutboxRepository

logger = logging.getLogger(__name__)


class OutboxRelay:
    def __init__(
        self,
        broker,
        session_factory,
        *,
        poll_seconds: float = 1.0,
        batch_size: int = 100,
        max_attempts: int = 5,
    ) -> None:
        self._broker = broker
        self._session_factory = session_factory
        self._poll_seconds = poll_seconds
        self._batch_size = batch_size
        self._max_attempts = max_attempts

    async def flush_once(self) -> int:
        """Publish one batch of pending events; return how many were published."""
        published = 0
        async with self._session_factory() as session:
            repo = OutboxRepository(session)
            events = await repo.claim_batch(batch_size=self._batch_size)
            if not events:
                await session.rollback()  # release the row locks
                return 0
            for event in events:
                try:
                    message = decode(event.fields)
                    await self._broker.publish(event.stream, message)
                    await repo.mark_delivered(event.id)
                    published += 1
                except Exception as exc:
                    logger.exception(
                        "outbox_publish_failed id=%s stream=%s kind=%s",
                        event.id,
                        event.stream,
                        event.kind,
                    )
                    await repo.mark_failed(
                        event.id, str(exc), max_attempts=self._max_attempts
                    )
            await session.commit()
        return published

    async def run_forever(self) -> None:
        """Poll and publish pending events until cancelled."""
        logger.info(
            "outbox_relay_started poll_seconds=%s batch_size=%s",
            self._poll_seconds,
            self._batch_size,
        )
        while True:
            try:
                published = await self.flush_once()
                if published:
                    logger.info("outbox_relay_published count=%s", published)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("outbox_relay_flush_failed")
            await asyncio.sleep(self._poll_seconds)
