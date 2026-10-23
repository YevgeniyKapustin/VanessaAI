from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from vanessa.pipeline.schedule.cron import (
    day_matches,
    next_local_run,
    next_run_utc,
    parse_cron,
    parse_field,
)

# Fixed +4 offset: the dev host may have no IANA zone data.
TZ = timezone(timedelta(hours=4))
# Wednesday 2026-10-21, 12:00 local.
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)


def test_parse_fields() -> None:
    spec = parse_cron("0 13 * * 5")
    assert spec.minutes == (0,)
    assert spec.hours == (13,)
    assert spec.weekdays == frozenset({5})
    assert spec.any_day is True
    assert spec.any_weekday is False


def test_seven_is_sunday() -> None:
    assert parse_cron("0 9 * * 7").weekdays == frozenset({0})


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("*/20", {0, 20, 40}),
        ("10/20", {10, 30, 50}),
        ("1-3,7", {1, 2, 3, 7}),
        ("5-15/5", {5, 10, 15}),
    ],
)
def test_parse_field_forms(text: str, expected: set[int]) -> None:
    assert parse_field(text, 0, 59) == frozenset(expected)


@pytest.mark.parametrize(
    "expr",
    ["0 13 * *", "60 * * * *", "*/0 * * * *", "a * * * *", "5-3 * * * *", "0 0 0 * *"],
)
def test_invalid_cron_raises(expr: str) -> None:
    with pytest.raises(ValueError, match=r"cron|number"):
        parse_cron(expr)


def test_next_friday_in_local_zone() -> None:
    run = next_run_utc(parse_cron("0 13 * * 5"), NOW, TZ)
    assert run == datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
    assert run.tzinfo is UTC


def test_next_run_is_strictly_after() -> None:
    first = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
    run = next_run_utc(parse_cron("0 13 * * 5"), first, TZ)
    assert run == first + timedelta(days=7)


def test_same_day_later_hour() -> None:
    run = next_run_utc(parse_cron("30 9,18 * * *"), NOW, TZ)
    assert run == datetime(2026, 10, 21, 14, 30, tzinfo=UTC)


def test_day_or_weekday_when_both_restricted() -> None:
    spec = parse_cron("0 9 1 * 1")
    assert day_matches(spec, date(2026, 10, 26)) is True  # Monday
    assert day_matches(spec, date(2026, 11, 1)) is True  # 1st, a Sunday
    assert day_matches(spec, date(2026, 10, 27)) is False


def test_day_and_weekday_when_one_is_star() -> None:
    spec = parse_cron("0 9 1 * *")
    assert day_matches(spec, date(2026, 11, 1)) is True
    assert day_matches(spec, date(2026, 10, 26)) is False


def test_month_filter() -> None:
    assert day_matches(parse_cron("0 9 * 12 *"), date(2026, 10, 26)) is False


def test_impossible_date_has_no_run() -> None:
    assert next_local_run(parse_cron("0 0 30 2 *"), NOW.astimezone(TZ)) is None
    assert next_run_utc(parse_cron("0 0 30 2 *"), NOW, TZ) is None
