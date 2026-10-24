"""The current message carries the weekday; history labels do not.

Labels use the process time zone, so the checks use a Saturday noon and
skip the hour: the date stays the same in any zone within 11 hours of UTC.
"""

from datetime import UTC, datetime

from vanessa.core.message_time import format_current_time, format_message_time
from vanessa.pipeline.llm.prompts.prompt_format import format_current_message

SATURDAY_NOON = datetime(2026, 1, 3, 12, 0, tzinfo=UTC)


def test_current_time_names_the_weekday() -> None:
    label = format_current_time(SATURDAY_NOON)
    assert label.startswith("03.01.2026 ")
    assert label.endswith(", Saturday")


def test_history_label_has_no_weekday() -> None:
    label = format_message_time(SATURDAY_NOON)
    assert label.startswith("03.01.2026 ")
    assert "Saturday" not in label


def test_unknown_time_label() -> None:
    assert format_message_time(None) == "??.??.???? ??:??"


def test_current_message_shows_the_weekday() -> None:
    rendered = format_current_message("hello", created_at=SATURDAY_NOON)
    assert ", Saturday" in rendered
