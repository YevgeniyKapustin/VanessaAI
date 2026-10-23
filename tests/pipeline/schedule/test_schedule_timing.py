from datetime import UTC, datetime, timedelta, timezone

import pytest

from vanessa.config.settings import settings
from vanessa.pipeline.decision.schedule_request import ScheduleRequest
from vanessa.pipeline.schedule.cron import parse_cron
from vanessa.pipeline.schedule.timing import (
    SchedulePolicy,
    first_run,
    format_local,
    min_gap,
    next_cron_run,
    parse_local_iso,
    planner_now_text,
    schedule_policy,
    schedule_zone,
    upcoming_runs,
)

TZ = timezone(timedelta(hours=4), "Asia/Tbilisi")
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)  # Wed 12:00 local
POLICY = SchedulePolicy(tz=TZ)


def _cron(cron: str) -> ScheduleRequest:
    return ScheduleRequest(action="add", cron=cron, text="x")


def _once(at: str) -> ScheduleRequest:
    return ScheduleRequest(action="add", at=at, text="x")


def test_zone_utc_and_unknown_fallback() -> None:
    assert schedule_zone("UTC") is UTC
    assert schedule_zone("Nowhere/Atlantis") is UTC


def test_policy_reads_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "schedule_timezone", "UTC")
    cap = 3
    monkeypatch.setattr(settings, "schedule_max_per_chat", cap)
    monkeypatch.setattr(settings, "schedule_min_interval_minutes", 60)
    policy = schedule_policy()
    assert policy.tz is UTC
    assert policy.max_per_chat == cap
    assert policy.min_interval == timedelta(hours=1)


def test_default_zone_is_tbilisi() -> None:
    assert type(settings).model_fields["schedule_timezone"].default == "Asia/Tbilisi"


def test_cron_first_run() -> None:
    run, reason = first_run(_cron("0 13 * * 5"), NOW, POLICY)
    assert (run, reason) == (datetime(2026, 10, 23, 9, 0, tzinfo=UTC), "")


@pytest.mark.parametrize(
    ("cron", "reason"),
    [("*/10 * * * *", "too_frequent"), ("bad", "bad_cron"), ("0 0 30 2 *", "bad_cron")],
)
def test_cron_rejects(cron: str, reason: str) -> None:
    assert first_run(_cron(cron), NOW, POLICY) == (None, reason)


def test_every_half_hour_is_allowed() -> None:
    run, reason = first_run(_cron("*/30 * * * *"), NOW, POLICY)
    assert reason == ""
    assert run == datetime(2026, 10, 21, 8, 30, tzinfo=UTC)


def test_once_local_time_to_utc() -> None:
    run, reason = first_run(_once("2026-10-22T10:00"), NOW, POLICY)
    assert (run, reason) == (datetime(2026, 10, 22, 6, 0, tzinfo=UTC), "")


def test_once_with_offset_keeps_offset() -> None:
    assert parse_local_iso("2026-10-22T10:00+00:00", TZ) == datetime(
        2026, 10, 22, 10, 0, tzinfo=UTC
    )


@pytest.mark.parametrize(
    ("at", "reason"),
    [("завтра", "bad_time"), ("2026-10-20T10:00", "past"), ("2028-01-01T10:00", "too_far")],
)
def test_once_rejects(at: str, reason: str) -> None:
    assert first_run(_once(at), NOW, POLICY) == (None, reason)


def test_next_cron_run_bad_cron() -> None:
    assert next_cron_run("nope", NOW, TZ) is None
    assert next_cron_run("0 13 * * 5", NOW, TZ) == datetime(2026, 10, 23, 9, tzinfo=UTC)


def test_upcoming_runs_and_gap() -> None:
    runs = upcoming_runs(parse_cron("0 13 * * 1,5"), NOW, TZ)
    assert runs[0] == datetime(2026, 10, 23, 9, tzinfo=UTC)
    assert min_gap(runs) == timedelta(days=3)
    assert min_gap(runs[:1]) is None


def test_format_local_has_no_zone_name() -> None:
    text = format_local(datetime(2026, 10, 23, 9, tzinfo=UTC), TZ)
    assert text == "2026-10-23 13:00 (пятница)"
    assert "Tbilisi" not in text
    assert "+04" not in text


def test_planner_now_text_has_no_zone(monkeypatch) -> None:
    monkeypatch.setattr(settings, "schedule_timezone", "UTC")
    assert planner_now_text(NOW) == "2026-10-21 08:00 (среда)"
    assert planner_now_text()
