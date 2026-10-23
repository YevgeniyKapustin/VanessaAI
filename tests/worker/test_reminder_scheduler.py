from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.worker.reminders.scheduler import (
    OUTBOUND_SOURCE,
    ReminderScheduler,
    outbound_message,
)
from tests.worker.hermes_fakes import FakeBroker
from vanessa.contracts.outbound import OutboundMessage
from vanessa.core.reminders import Reminder
from vanessa.infrastructure.db.reminder_models import ReminderRow

CHAT = -100500
STREAM = "vanessa:outbound"
TZ = timezone(timedelta(hours=4))
DUE = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)  # Fri 13:00 local
URL = "https://example.com/menu"


class _Composer:
    async def compose(self, reminder: Reminder) -> str:
        return reminder.text


def _row(rid: int = 1, *, cron: str = "0 13 * * 5", at: datetime = DUE) -> ReminderRow:
    return ReminderRow(
        id=rid,
        channel="telegram",
        chat_id=CHAT,
        text=f"Обеды! {URL}",
        cron=cron,
        next_run_at=at,
        created_by=7,
    )


def _session(rows: list[ReminderRow]) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute.return_value = result
    return session


def _scheduler(session: AsyncMock, broker: FakeBroker) -> ReminderScheduler:
    @asynccontextmanager
    async def factory():
        yield session

    return ReminderScheduler(
        factory, broker, _Composer(), outbound_stream=STREAM, tz=TZ, poll_seconds=0.0
    )


def test_outbound_message_is_stable_per_run() -> None:
    reminder = Reminder(id=3, chat_id=CHAT, text="t", next_run_at=DUE)
    message = outbound_message(reminder, "t")
    assert message.message_id == f"reminder-3-{int(DUE.timestamp())}"
    assert message.telegram_chat_id == CHAT
    assert message.source == OUTBOUND_SOURCE
    assert message.reply_to_message_id is None


async def test_cron_post_fires_and_moves_to_next_week() -> None:
    row, broker = _row(), FakeBroker()
    session = _session([row])
    posted = await _scheduler(session, broker).tick(DUE + timedelta(seconds=20))
    assert posted == 1
    ((stream, message),) = broker.published
    assert stream == STREAM
    assert isinstance(message, OutboundMessage)
    assert URL in message.text
    assert row.next_run_at == DUE + timedelta(days=7)
    session.delete.assert_not_awaited()
    session.commit.assert_awaited_once()


async def test_once_post_is_removed_after_fire() -> None:
    row, broker = _row(cron=""), FakeBroker()
    session = _session([row])
    assert await _scheduler(session, broker).tick(DUE) == 1
    session.delete.assert_awaited_once_with(row)


async def test_publish_failure_keeps_row_due() -> None:
    row = _row()
    session = _session([row])
    broker = FakeBroker(error=RuntimeError("redis down"))
    assert await _scheduler(session, broker).tick(DUE) == 0
    assert row.next_run_at == DUE
    session.delete.assert_not_awaited()


async def test_stale_post_is_skipped_and_advanced() -> None:
    row, broker = _row(), FakeBroker()
    session = _session([row])
    assert await _scheduler(session, broker).tick(DUE + timedelta(hours=5)) == 0
    assert broker.published == []
    assert row.next_run_at == DUE + timedelta(days=7)


async def test_broken_cron_is_removed() -> None:
    row, broker = _row(cron="bad cron"), FakeBroker()
    session = _session([row])
    assert await _scheduler(session, broker).tick(DUE) == 1
    session.delete.assert_awaited_once_with(row)


class _Stop(BaseException):
    """Ends the endless loop in the test (not caught by ``except Exception``)."""


async def test_run_forever_survives_tick_error(monkeypatch) -> None:
    scheduler = _scheduler(_session([]), FakeBroker())
    calls = 0

    async def tick(now=None) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("db down")
        raise _Stop

    monkeypatch.setattr(scheduler, "tick", tick)
    with pytest.raises(_Stop):
        await scheduler.run_forever()
    assert calls == len(["failed tick", "stop tick"])
