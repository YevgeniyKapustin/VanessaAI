"""Fire due scheduled posts to the ``outbound`` stream.

One tick is one transaction: claim due rows with ``FOR UPDATE SKIP LOCKED``
(a second worker skips them), post each one, then move a recurring post to
its next run or delete a one-shot post. A failed publish keeps the row, so
the next tick retries it. A post more late than ``max_late`` (the worker was
down) is not sent; it only moves on. The ``message_id`` is fixed per run, so
the bot drops a duplicate if a commit fails after a publish.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta, tzinfo

from services.worker.reminders.compose import ReminderComposer
from vanessa.contracts.outbound import OutboundMessage
from vanessa.core.reminders import Reminder
from vanessa.infrastructure.db.reminder_models import ReminderRow
from vanessa.infrastructure.db.reminder_repository import (
    ReminderRepository,
    to_reminder,
)
from vanessa.pipeline.schedule.timing import next_cron_run

logger = logging.getLogger(__name__)

OUTBOUND_SOURCE = "reminder"


def outbound_message(reminder: Reminder, text: str) -> OutboundMessage:
    run_key = int(reminder.next_run_at.timestamp())
    return OutboundMessage(
        message_id=f"reminder-{reminder.id}-{run_key}",
        channel="telegram",
        telegram_chat_id=reminder.chat_id,
        text=text,
        source=OUTBOUND_SOURCE,
    )


class ReminderScheduler:
    """Polling loop that owns the fire / advance cycle of scheduled posts."""

    def __init__(
        self,
        session_factory,
        broker,
        composer: ReminderComposer,
        *,
        outbound_stream: str,
        tz: tzinfo,
        poll_seconds: float = 30.0,
        max_late: timedelta = timedelta(hours=3),
        batch_size: int = 20,
    ) -> None:
        self._factory = session_factory
        self._broker = broker
        self._composer = composer
        self._stream = outbound_stream
        self._tz = tz
        self._poll_seconds = poll_seconds
        self._max_late = max_late
        self._batch_size = batch_size

    async def run_forever(self) -> None:
        logger.info("reminder_scheduler_started poll_seconds=%s", self._poll_seconds)
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("reminder_tick_failed")
            await asyncio.sleep(self._poll_seconds)

    async def tick(self, now: datetime | None = None) -> int:
        """Fire every due post once; return how many were published."""
        now = now or datetime.now(UTC)
        async with self._factory() as session:
            repo = ReminderRepository(session)
            rows = await repo.claim_due(now=now, limit=self._batch_size)
            posted = 0
            for row in rows:
                posted += await self._fire(repo, row, now)
            await session.commit()
        return posted

    async def _fire(self, repo: ReminderRepository, row: ReminderRow, now: datetime) -> int:
        reminder = to_reminder(row)
        if now - reminder.next_run_at > self._max_late:
            logger.warning("reminder_skipped_stale reminder_id=%s", reminder.id)
            await self._advance(repo, row, now)
            return 0
        if not await self._post(reminder):
            return 0
        await self._advance(repo, row, now)
        return 1

    async def _post(self, reminder: Reminder) -> bool:
        text = await self._composer.compose(reminder)
        try:
            await self._broker.publish(self._stream, outbound_message(reminder, text))
        except Exception:
            logger.exception("reminder_publish_failed reminder_id=%s", reminder.id)
            return False
        logger.info(
            "reminder_posted reminder_id=%s chat_id=%s once=%s len=%s",
            reminder.id,
            reminder.chat_id,
            reminder.is_once,
            len(text),
        )
        return True

    async def _advance(self, repo: ReminderRepository, row: ReminderRow, now: datetime) -> None:
        upcoming = None
        if row.cron:
            upcoming = next_cron_run(row.cron, max(now, row.next_run_at), self._tz)
        if upcoming is None:
            await repo.remove(row)
            return
        row.next_run_at = upcoming


__all__ = ["OUTBOUND_SOURCE", "ReminderScheduler", "outbound_message"]
