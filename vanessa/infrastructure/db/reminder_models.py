"""ORM row for scheduled chat posts (migration ``012_reminders``)."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from vanessa.infrastructure.db.base import Base


class ReminderRow(Base):
    """One scheduled post: recurring (``cron``) or one-shot (``cron`` empty)."""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="telegram"
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # 5-field cron in the schedule timezone; "" for a one-shot post.
    cron: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_reminders_next_run_at", "next_run_at"),
        Index("ix_reminders_chat_id", "chat_id"),
    )
