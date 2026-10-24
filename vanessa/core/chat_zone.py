"""The chat's local time zone (``SCHEDULE_TIMEZONE``).

Storage stays UTC. Every time Vanessa sees (message labels, the current
weekday, activity hours, card dates) and every reminder time uses this
zone, so «12:33» in the prompt is 12:33 in the chat.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from vanessa.config.settings import settings

logger = logging.getLogger(__name__)


@lru_cache
def schedule_zone(name: str) -> tzinfo:
    """IANA zone by name; UTC when the name is unknown on this host."""
    if name.strip().upper() == "UTC":
        return UTC
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("schedule_timezone_unknown name=%s fallback=UTC", name)
        return UTC


def chat_zone() -> tzinfo:
    return schedule_zone(settings.schedule_timezone)


def to_chat_time(value: datetime) -> datetime:
    """An aware moment in the chat zone; a naive value is taken as UTC."""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(chat_zone())


def chat_now() -> datetime:
    return datetime.now(chat_zone())
