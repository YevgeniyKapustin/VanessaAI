from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from vanessa.core.reminders import NewReminder
from vanessa.infrastructure.db.reminder_models import ReminderRow
from vanessa.infrastructure.db.reminder_repository import (
    ReminderRepository,
    SessionReminderStore,
    create_reminder_store,
    to_reminder,
)

WHEN = datetime(2026, 10, 23, 9, tzinfo=UTC)
NEW = NewReminder(chat_id=-1, text="Обеды", next_run_at=WHEN, cron="0 13 * * 5", created_by=7)


def _row(rid: int = 1) -> ReminderRow:
    return ReminderRow(
        id=rid, channel=None, chat_id=-1, text="Обеды", cron=None, next_run_at=WHEN
    )


def _session(rows=(), rowcount: int | None = 1) -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows)
    result.rowcount = rowcount
    session.execute.return_value = result
    return session


def test_to_reminder_defaults() -> None:
    reminder = to_reminder(_row())
    assert (reminder.cron, reminder.channel, reminder.is_once) == ("", "telegram", True)


async def test_add_flushes_row() -> None:
    session = _session()
    reminder = await ReminderRepository(session).add(NEW)
    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    assert (reminder.text, reminder.cron, reminder.created_by) == ("Обеды", "0 13 * * 5", 7)


async def test_list_and_claim() -> None:
    session = _session([_row(1), _row(2)])
    repo = ReminderRepository(session)
    assert [r.id for r in await repo.list_for_chat(-1)] == [1, 2]
    rows = await repo.claim_due(now=WHEN, limit=5)
    assert [r.id for r in rows] == [1, 2]
    sql = str(session.execute.await_args.args[0])
    assert "FOR UPDATE" in sql.upper()


async def test_delete_ids() -> None:
    ids = [1, 2]
    repo = ReminderRepository(_session(rowcount=len(ids)))
    assert await repo.delete_ids(-1, ids) == len(ids)
    assert await repo.delete_ids(-1, []) == 0
    assert await ReminderRepository(_session(rowcount=None)).delete_ids(-1, [1]) == 0


async def test_remove() -> None:
    session = _session()
    row = _row()
    await ReminderRepository(session).remove(row)
    session.delete.assert_awaited_once_with(row)


async def test_session_store_commits() -> None:
    session = _session([_row()], rowcount=1)

    @asynccontextmanager
    async def factory():
        yield session

    store = SessionReminderStore(factory)
    assert (await store.add(NEW)).text == "Обеды"
    assert len(await store.list_for_chat(-1)) == 1
    assert await store.delete(-1, [1]) == 1
    # add and delete commit; list only reads.
    assert session.commit.await_count == len(["add", "delete"])


def test_create_store() -> None:
    assert create_reminder_store(SimpleNamespace(schedule_enabled=False)) is None
    store = create_reminder_store(SimpleNamespace(schedule_enabled=True), object())
    assert isinstance(store, SessionReminderStore)
