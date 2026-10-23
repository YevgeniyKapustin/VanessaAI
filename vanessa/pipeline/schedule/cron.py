"""Minimal 5-field cron: ``minute hour day month weekday`` (numbers only).

Each field takes ``*``, ``n``, ``a-b``, ``*/s``, ``a-b/s``, ``n/s`` and comma
lists. Weekday is 0-7 (0 and 7 are Sunday). As in classic cron, when both day
and weekday are restricted, a date matches if either one matches.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

_FIELD_COUNT = 5
_SUNDAY = 7
# Search window for the next run; Feb 29 fits in it.
_SEARCH_DAYS = 366 * 5
_BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


@dataclass(frozen=True, slots=True)
class CronSpec:
    minutes: tuple[int, ...]
    hours: tuple[int, ...]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    any_day: bool
    any_weekday: bool


def _number(text: str) -> int:
    if not text.isdigit():
        raise ValueError(f"not a number: {text!r}")
    return int(text)


def _split_step(part: str) -> tuple[str, int, bool]:
    base, sep, step_text = part.partition("/")
    if not sep:
        return base, 1, False
    step = _number(step_text)
    if step < 1:
        raise ValueError("cron step must be positive")
    return base, step, True


def _span(base: str, lo: int, hi: int, *, open_end: bool) -> tuple[int, int]:
    if base == "*":
        return lo, hi
    first, sep, last = base.partition("-")
    start = _number(first)
    end = _number(last) if sep else (hi if open_end else start)
    if start < lo or end > hi or start > end:
        raise ValueError(f"cron value out of range: {base!r}")
    return start, end


def _parse_part(part: str, lo: int, hi: int) -> set[int]:
    base, step, stepped = _split_step(part)
    start, end = _span(base, lo, hi, open_end=stepped)
    return set(range(start, end + 1, step))


def parse_field(text: str, lo: int, hi: int) -> frozenset[int]:
    values: set[int] = set()
    for part in text.split(","):
        values |= _parse_part(part, lo, hi)
    return frozenset(values)


def parse_cron(expr: str) -> CronSpec:
    """Parse a cron expression; raise ``ValueError`` when it is invalid."""
    fields = expr.split()
    if len(fields) != _FIELD_COUNT:
        raise ValueError("cron needs 5 fields")
    parsed = [
        parse_field(text, lo, hi)
        for text, (lo, hi) in zip(fields, _BOUNDS, strict=True)
    ]
    weekdays = frozenset(day % _SUNDAY for day in parsed[4])
    return CronSpec(
        minutes=tuple(sorted(parsed[0])),
        hours=tuple(sorted(parsed[1])),
        days=parsed[2],
        months=parsed[3],
        weekdays=weekdays,
        any_day=fields[2] == "*",
        any_weekday=fields[4] == "*",
    )


def _cron_weekday(day: date) -> int:
    return (day.weekday() + 1) % _SUNDAY


def day_matches(spec: CronSpec, day: date) -> bool:
    if day.month not in spec.months:
        return False
    by_day = day.day in spec.days
    by_weekday = _cron_weekday(day) in spec.weekdays
    if spec.any_day or spec.any_weekday:
        return by_day and by_weekday
    return by_day or by_weekday


def _first_on_day(spec: CronSpec, day: date, after: datetime) -> datetime | None:
    for hour in spec.hours:
        for minute in spec.minutes:
            candidate = datetime.combine(day, time(hour, minute), tzinfo=after.tzinfo)
            if candidate > after:
                return candidate
    return None


def next_local_run(spec: CronSpec, after: datetime) -> datetime | None:
    """First matching local time strictly after ``after`` (an aware datetime)."""
    start = after.date()
    for offset in range(_SEARCH_DAYS):
        day = start + timedelta(days=offset)
        if not day_matches(spec, day):
            continue
        found = _first_on_day(spec, day, after)
        if found is not None:
            return found
    return None


def next_run_utc(spec: CronSpec, after_utc: datetime, tz: tzinfo) -> datetime | None:
    """Next run as a UTC datetime; cron fields are read in ``tz``."""
    local = next_local_run(spec, after_utc.astimezone(tz))
    if local is None:
        return None
    return local.astimezone(after_utc.tzinfo)


__all__ = [
    "CronSpec",
    "day_matches",
    "next_local_run",
    "next_run_utc",
    "parse_cron",
    "parse_field",
]
