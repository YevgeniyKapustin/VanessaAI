"""Time rules for scheduled posts: zone, first run, next run, frequency."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from functools import lru_cache
from itertools import pairwise
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from vanessa.config.settings import settings
from vanessa.pipeline.decision.schedule_request import ScheduleRequest
from vanessa.pipeline.schedule.cron import CronSpec, next_run_utc, parse_cron

logger = logging.getLogger(__name__)

MAX_AHEAD = timedelta(days=366)
# Frequency check: runs inside this window (a week covers weekday patterns).
_GAP_HORIZON = timedelta(days=8)
_GAP_SAMPLES = 64
_WEEKDAYS = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)


@dataclass(frozen=True, slots=True)
class SchedulePolicy:
    tz: tzinfo
    max_per_chat: int = 20
    min_interval: timedelta = timedelta(minutes=30)
    text_max_chars: int = 1000


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


def schedule_policy() -> SchedulePolicy:
    return SchedulePolicy(
        tz=schedule_zone(settings.schedule_timezone),
        max_per_chat=settings.schedule_max_per_chat,
        min_interval=timedelta(minutes=settings.schedule_min_interval_minutes),
        text_max_chars=settings.schedule_text_max_chars,
    )


def next_cron_run(cron: str, after_utc: datetime, tz: tzinfo) -> datetime | None:
    """Next UTC run of ``cron`` after ``after_utc``; None for a bad cron."""
    try:
        spec = parse_cron(cron)
    except ValueError:
        return None
    return next_run_utc(spec, after_utc, tz)


def _within_horizon(run: datetime, start: datetime, runs: list[datetime]) -> bool:
    return not runs or run - start <= _GAP_HORIZON


def upcoming_runs(spec: CronSpec, after_utc: datetime, tz: tzinfo) -> list[datetime]:
    runs: list[datetime] = []
    cursor = after_utc
    while len(runs) < _GAP_SAMPLES:
        run = next_run_utc(spec, cursor, tz)
        if run is None or not _within_horizon(run, after_utc, runs):
            break
        runs.append(run)
        cursor = run
    return runs


def min_gap(runs: list[datetime]) -> timedelta | None:
    gaps = [later - earlier for earlier, later in pairwise(runs)]
    return min(gaps) if gaps else None


def _cron_first_run(
    cron: str, now_utc: datetime, policy: SchedulePolicy
) -> tuple[datetime | None, str]:
    try:
        spec = parse_cron(cron)
    except ValueError:
        return None, "bad_cron"
    runs = upcoming_runs(spec, now_utc, policy.tz)
    if not runs:
        return None, "bad_cron"
    gap = min_gap(runs)
    if gap is not None and gap < policy.min_interval:
        return None, "too_frequent"
    return runs[0], ""


def parse_local_iso(text: str, tz: tzinfo) -> datetime | None:
    """``YYYY-MM-DDTHH:MM`` in ``tz`` (or with an offset) → UTC."""
    try:
        parsed = datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(UTC)


def _once_first_run(
    at: str, now_utc: datetime, policy: SchedulePolicy
) -> tuple[datetime | None, str]:
    run = parse_local_iso(at, policy.tz)
    if run is None:
        return None, "bad_time"
    if run <= now_utc:
        return None, "past"
    if run - now_utc > MAX_AHEAD:
        return None, "too_far"
    return run, ""


def first_run(
    request: ScheduleRequest, now_utc: datetime, policy: SchedulePolicy
) -> tuple[datetime | None, str]:
    """First UTC run and an empty reason, or None and a reject reason."""
    if request.cron:
        return _cron_first_run(request.cron, now_utc, policy)
    return _once_first_run(request.at, now_utc, policy)


def format_local(moment: datetime, tz: tzinfo) -> str:
    local = moment.astimezone(tz)
    return f"{local:%Y-%m-%d %H:%M} ({_WEEKDAYS[local.weekday()]})"


def planner_now_text(now_utc: datetime | None = None) -> str:
    """Current local time for the planner prompt (date and weekday only).

    No zone name: Vanessa never mentions a time zone in the chat.
    """
    moment = now_utc or datetime.now(UTC)
    return format_local(moment, schedule_zone(settings.schedule_timezone))


__all__ = [
    "MAX_AHEAD",
    "SchedulePolicy",
    "first_run",
    "format_local",
    "min_gap",
    "next_cron_run",
    "parse_local_iso",
    "planner_now_text",
    "schedule_policy",
    "schedule_zone",
    "upcoming_runs",
]
