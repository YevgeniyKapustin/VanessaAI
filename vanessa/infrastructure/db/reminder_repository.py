"""Postgres access for scheduled chat posts.

``ReminderRepository`` works on one open session (the scheduler keeps the
claim lock for the whole fire batch). ``SessionReminderStore`` opens a short
session per call for the turn pipeline (add / list / cancel).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vanessa.core.reminders import NewReminder, Reminder
from vanessa.infrastructure.db.reminder_models import ReminderRow
from vanessa.infrastructure.db.session import async_session_factory


def to_reminder(row: ReminderRow) -> Reminder:
    return Reminder(
        id=row.id,
        chat_id=row.chat_id,
        text=row.text,
        next_run_at=row.next_run_at,
        cron=row.cron or "",
        created_by=row.created_by,
        channel=row.channel or "telegram",
    )


class ReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, new: NewReminder) -> Reminder:
        row = ReminderRow(
            channel=new.channel,
            chat_id=new.chat_id,
            text=new.text,
            cron=new.cron,
            next_run_at=new.next_run_at,
            created_by=new.created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return to_reminder(row)

    async def list_for_chat(self, chat_id: int) -> list[Reminder]:
        result = await self._session.execute(
            select(ReminderRow)
            .where(ReminderRow.chat_id == chat_id)
            .order_by(ReminderRow.id)
        )
        return [to_reminder(row) for row in result.scalars().all()]

    async def delete_ids(self, chat_id: int, ids: list[int]) -> int:
        if not ids:
            return 0
        result = await self._session.execute(
            delete(ReminderRow)
            .where(ReminderRow.chat_id == chat_id)
            .where(ReminderRow.id.in_(ids))
        )
        return int(result.rowcount or 0)

    async def claim_due(self, *, now: datetime, limit: int) -> list[ReminderRow]:
        """Lock due rows for this process; other workers skip them."""
        result = await self._session.execute(
            select(ReminderRow)
            .where(ReminderRow.next_run_at <= now)
            .order_by(ReminderRow.next_run_at, ReminderRow.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def remove(self, row: ReminderRow) -> None:
        await self._session.delete(row)


class SessionReminderStore:
    """``ReminderStoreProtocol`` over a session factory (one commit per call)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def add(self, new: NewReminder) -> Reminder:
        async with self._factory() as session:
            reminder = await ReminderRepository(session).add(new)
            await session.commit()
            return reminder

    async def list_for_chat(self, chat_id: int) -> list[Reminder]:
        async with self._factory() as session:
            return await ReminderRepository(session).list_for_chat(chat_id)

    async def delete(self, chat_id: int, ids: list[int]) -> int:
        async with self._factory() as session:
            count = await ReminderRepository(session).delete_ids(chat_id, ids)
            await session.commit()
            return count


def create_reminder_store(
    settings, session_factory: async_sessionmaker[AsyncSession] | None = None
) -> SessionReminderStore | None:
    """The Postgres store, or None when the skill is off."""
    if not settings.schedule_enabled:
        return None
    return SessionReminderStore(session_factory or async_session_factory)


__all__ = [
    "ReminderRepository",
    "SessionReminderStore",
    "create_reminder_store",
    "to_reminder",
]
