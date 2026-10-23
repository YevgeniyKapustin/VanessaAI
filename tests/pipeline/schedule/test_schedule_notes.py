import re
from datetime import UTC, datetime, timedelta, timezone

import pytest

from vanessa.config.content_schedule import get_schedule_content, load_schedule_content
from vanessa.core.reminders import Reminder
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder
from vanessa.pipeline.llm.prompts.prompt_schedule import schedule_parts
from vanessa.pipeline.schedule.actions import ScheduleOutcome
from vanessa.pipeline.schedule.notes import describe_when, render_items, render_note
from vanessa.pipeline.schedule.timing import SchedulePolicy

TZ = timezone(timedelta(hours=4), "Asia/Tbilisi")
POLICY = SchedulePolicy(tz=TZ, max_per_chat=20, min_interval=timedelta(minutes=30))
WHEN = datetime(2026, 10, 23, 9, tzinfo=UTC)
WEEKLY = Reminder(id=1, chat_id=-1, text="Обеды! https://e.x/m", next_run_at=WHEN, cron="0 13 * * 5")
ONCE = Reminder(id=2, chat_id=-1, text="Созвон", next_run_at=WHEN)
# Zone names Vanessa must never say in the chat (rendered data only).
ZONE_RE = re.compile(r"UTC|GMT|MSK|МСК|Tbilisi|Тбилис|Asia/|\+04", re.IGNORECASE)


@pytest.fixture
def content():
    return get_schedule_content()


def test_when_texts_have_no_zone(content) -> None:
    weekly = describe_when(WEEKLY, content, POLICY)
    once = describe_when(ONCE, content, POLICY)
    assert "2026-10-23 13:00 (пятница)" in weekly
    assert "0 13 * * 5" in weekly
    assert once.startswith("один раз")
    assert not ZONE_RE.search(weekly + once)
    items = render_items((WEEKLY, ONCE), content, POLICY)
    assert items.startswith("1. ")
    assert "\n2. " in items
    assert not ZONE_RE.search(items)


def test_added_note(content) -> None:
    note = render_note(ScheduleOutcome("added", (WEEKLY,)), content, POLICY)
    assert "https://e.x/m" in note
    assert "13:00" in note


def test_exists_note_says_nothing_was_added(content) -> None:
    note = render_note(ScheduleOutcome("exists", (WEEKLY,)), content, POLICY)
    assert "https://e.x/m" in note
    assert "13:00" in note
    assert "already" in note
    assert "NOTHING new" in note


@pytest.mark.parametrize("status", ["listed", "cancelled", "not_found", "ambiguous"])
def test_listing_notes_carry_items(content, status: str) -> None:
    note = render_note(ScheduleOutcome(status, (WEEKLY, ONCE)), content, POLICY)
    assert "1. " in note
    assert "Созвон" in note


@pytest.mark.parametrize(
    ("detail", "needle"),
    [("too_frequent", "30"), ("limit", "20"), ("past", "прошло"), ("weird", "weird")],
)
def test_rejected_reasons(content, detail: str, needle: str) -> None:
    note = render_note(ScheduleOutcome("rejected", detail=detail), content, POLICY)
    assert needle in note
    assert "NOT schedule" in note


def test_fixed_and_unknown_notes(content) -> None:
    assert render_note(ScheduleOutcome("empty"), content, POLICY) == content.empty_note.strip()
    error = content.error_note.strip()
    assert render_note(ScheduleOutcome("error"), content, POLICY) == error
    assert render_note(ScheduleOutcome("???"), content, POLICY) == error


def test_prompts_forbid_zone_names(content) -> None:
    notes = (content.added_note, content.exists_note, content.listed_note)
    for text in (*notes, content.fire_task):
        assert "time zone" in text


def test_load_schedule_content(tmp_path) -> None:
    path = tmp_path / "schedule.yaml"
    path.write_text(
        "item: i\nwhen_cron: c\nwhen_once: o\nadded_note: a\nexists_note: x\n"
        "listed_note: l\n"
        "empty_note: e\ncancelled_note: c\nnot_found_note: n\nambiguous_note: a\n"
        "rejected_note: r\nerror_note: e\nfire_task: f\n",
        encoding="utf-8",
    )
    loaded = load_schedule_content(path)
    assert loaded.max_tokens == type(loaded).model_fields["max_tokens"].default
    assert loaded.reasons == {}


def test_schedule_parts() -> None:
    assert schedule_parts(None) == []
    assert schedule_parts("  ") == []
    assert schedule_parts(" note ")[0][1:] == ("directives", "note")


def test_note_reaches_compose_prompt() -> None:
    prompt = PromptBuilder().build_user_prompt("x", [], schedule_note="SCHEDULE-NOTE-1")
    assert "SCHEDULE-NOTE-1" in prompt
