"""Time labels Vanessa sees use the chat zone; storage stays UTC."""

from datetime import UTC, datetime, timedelta

import pytest

from vanessa.config.settings import settings
from vanessa.core.chat_zone import chat_now, chat_zone, schedule_zone, to_chat_time
from vanessa.core.message_time import format_current_time, format_message_time
from vanessa.core.messages import ContextMessage
from vanessa.knowledge.format import today
from vanessa.knowledge.metrics.deterministic import _local_datetime
from vanessa.pipeline.llm.prompts.prompt_format import format_current_message
from vanessa.pipeline.llm.prompts.session_format import format_session_messages

#: Saturday morning in UTC; four hours later in the chat zone.
SATURDAY_UTC = datetime(2026, 1, 3, 8, 33, tzinfo=UTC)
#: Friday night in UTC is already Saturday in the chat zone.
FRIDAY_NIGHT_UTC = datetime(2026, 1, 2, 22, 30, tzinfo=UTC)
PLUS_FOUR = timedelta(hours=4)


@pytest.fixture(autouse=True)
def _chat_zone(monkeypatch) -> None:
    monkeypatch.setattr(settings, "schedule_timezone", "Asia/Tbilisi")


def test_current_time_is_local_with_weekday() -> None:
    assert format_current_time(SATURDAY_UTC) == "03.01.2026 12:33, Saturday"


def test_weekday_follows_the_local_date() -> None:
    assert format_current_time(FRIDAY_NIGHT_UTC) == "03.01.2026 02:30, Saturday"


def test_history_label_is_local_without_weekday() -> None:
    assert format_message_time(SATURDAY_UTC) == "03.01.2026 12:33"


def test_naive_value_is_taken_as_utc() -> None:
    naive = SATURDAY_UTC.replace(tzinfo=None)
    assert format_message_time(naive) == "03.01.2026 12:33"


def test_unknown_time_label() -> None:
    assert format_message_time(None) == "??.??.???? ??:??"


def test_utc_zone_keeps_utc_labels(monkeypatch) -> None:
    monkeypatch.setattr(settings, "schedule_timezone", "UTC")
    assert format_message_time(SATURDAY_UTC) == "03.01.2026 08:33"


def test_unknown_zone_falls_back_to_utc() -> None:
    assert schedule_zone("Nowhere/Atlantis") is UTC


def test_chat_time_helpers_use_the_zone() -> None:
    assert to_chat_time(SATURDAY_UTC).utcoffset() == PLUS_FOUR
    assert chat_now().utcoffset() == PLUS_FOUR
    assert chat_zone() is schedule_zone("Asia/Tbilisi")


def test_current_message_shows_local_time() -> None:
    rendered = format_current_message("hello", created_at=SATURDAY_UTC)
    assert "03.01.2026 12:33, Saturday" in rendered


def test_session_history_shows_local_time() -> None:
    message = ContextMessage(
        id=1, role="assistant", content="sample", created_at=SATURDAY_UTC
    )
    assert "03.01.2026 12:33" in format_session_messages([message])


def test_activity_hours_and_card_dates_use_the_zone() -> None:
    local = _local_datetime(FRIDAY_NIGHT_UTC)
    assert (local.day, local.hour) == (3, 2)
    assert today() == chat_now().date().isoformat()
