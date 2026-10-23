"""Scheduled chat posts ("reminders") Vanessa makes by herself.

A reminder is either recurring (``cron`` in the schedule timezone) or
one-shot (``cron`` is empty). ``next_run_at`` is always UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NewReminder:
    chat_id: int
    text: str
    next_run_at: datetime
    cron: str = ""
    created_by: int | None = None
    channel: str = "telegram"


@dataclass(frozen=True, slots=True)
class Reminder:
    id: int
    chat_id: int
    text: str
    next_run_at: datetime
    cron: str = ""
    created_by: int | None = None
    channel: str = "telegram"

    @property
    def is_once(self) -> bool:
        return not self.cron


__all__ = ["NewReminder", "Reminder"]
