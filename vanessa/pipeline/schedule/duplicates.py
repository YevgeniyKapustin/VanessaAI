"""Find a scheduled post that already covers a new add request.

The planner words the same post differently each time («выбирать обед» vs
«заказывать обед»), so the text alone does not prove a duplicate. A post
is the same when it runs on the same schedule and carries the same links;
a post without links must have the same text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime

from vanessa.core.reminders import Reminder
from vanessa.pipeline.schedule.urls import extract_urls

_NOT_WORD = re.compile(r"[\W_]+")


def _normalized(text: str) -> str:
    return _NOT_WORD.sub(" ", text.casefold()).strip()


def _same_schedule(reminder: Reminder, cron: str, run_at: datetime) -> bool:
    if cron:
        return reminder.cron == cron
    return reminder.is_once and reminder.next_run_at == run_at


def _same_post(reminder: Reminder, text: str) -> bool:
    urls = set(extract_urls(text))
    if urls:
        return set(extract_urls(reminder.text)) == urls
    return _normalized(reminder.text) == _normalized(text)


def find_duplicate(
    reminders: Iterable[Reminder], *, cron: str, run_at: datetime, text: str
) -> Reminder | None:
    """The first post with the same schedule and the same links or text."""
    for reminder in reminders:
        if _same_schedule(reminder, cron, run_at) and _same_post(reminder, text):
            return reminder
    return None


__all__ = ["find_duplicate"]
