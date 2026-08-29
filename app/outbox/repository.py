"""Transactional outbox repository.

Producers insert ``OutboxEvent`` rows in the same DB transaction as their
domain writes; the relay worker (``app.outbox.relay``) publishes them to the
broker afterwards. The claim/ack flow gives at-least-once delivery, and
consumers deduplicate by ``message_id``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.serialization import encode
from app.contracts.messages import BrokerMessage
from app.db.models import OutboxEvent


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, *, stream: str, message: BrokerMessage) -> None:
        """Stage a broker message for delivery (call before commit)."""
        fields = encode(message)
        self._session.add(
            OutboxEvent(
                stream=stream,
                kind=message.message_kind(),
                message_id=message.message_id,
                correlation_id=message.correlation_id,
                fields=fields,
            )
        )

    async def claim_batch(self, *, batch_size: int) -> list[OutboxEvent]:
        """Claim the oldest pending events, locking them for this worker."""
        result = await self._session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.status == "pending")
            .order_by(OutboxEvent.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def mark_delivered(self, event_id: int) -> None:
        await self._session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(
                status="delivered",
                delivered_at=datetime.now(timezone.utc),
            )
        )

    async def mark_failed(self, event_id: int, error: str, *, max_attempts: int = 5) -> None:
        """Bump attempts; move to ``failed`` once the cap is reached."""
        event = await self._session.get(OutboxEvent, event_id)
        if event is None:
            return
        event.attempts += 1
        event.last_error = error[:500]
        if event.attempts >= max_attempts:
            event.status = "failed"

    async def count_pending(self) -> int:
        result = await self._session.execute(
            select(OutboxEvent.id).where(OutboxEvent.status == "pending")
        )
        return len(result.scalars().all())
