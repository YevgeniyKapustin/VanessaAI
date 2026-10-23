from datetime import UTC, datetime

import pytest

from vanessa.core.reminders import Reminder
from vanessa.pipeline.schedule.matching import match_reminders, stem
from vanessa.pipeline.schedule.urls import extract_urls, keep_urls, urls_intact

URL = "https://example.com/menu_week?id=1&x=2"
WHEN = datetime(2026, 10, 23, 9, tzinfo=UTC)


def _reminder(rid: int, text: str) -> Reminder:
    return Reminder(id=rid, chat_id=-1, text=text, next_run_at=WHEN, cron="0 13 * * 5")


def test_extract_trims_prose_punctuation() -> None:
    text = f"обеды тут: {URL}. И ещё (см. https://a.b/c)! и снова {URL}"
    assert extract_urls(text) == [URL, "https://a.b/c"]


def test_extract_keeps_balanced_brackets() -> None:
    assert extract_urls("https://w.org/A_(b)") == ["https://w.org/A_(b)"]


def test_extract_empty() -> None:
    assert extract_urls("") == []


def test_keep_urls_appends_lost_link() -> None:
    assert keep_urls("Пятница, обеды!", f"кидай {URL}") == f"Пятница, обеды!\n{URL}"


def test_keep_urls_no_change_when_present() -> None:
    assert keep_urls(f"обеды {URL}", f"кидай {URL}") == f"обеды {URL}"


def test_urls_intact() -> None:
    assert urls_intact(f"обеды: {URL}", [URL]) is True
    assert urls_intact(f"[меню]({URL})", [URL]) is False
    assert urls_intact("обеды", [URL]) is False
    assert urls_intact("без ссылок", []) is True


@pytest.mark.parametrize(
    ("word", "expected"),
    [("обеды", "обед"), ("напоминалку", "напом"), ("мем", "мем")],
)
def test_stem(word: str, expected: str) -> None:
    assert stem(word) == expected


def test_empty_target_needs_single_post() -> None:
    one = [_reminder(1, "обеды")]
    two = [*one, _reminder(2, "созвон")]
    assert match_reminders(one, "") == one
    assert match_reminders(two, " ") is None


def test_all_target() -> None:
    posts = [_reminder(1, "обеды"), _reminder(2, "созвон")]
    assert match_reminders(posts, "Все") == posts


def test_numbers_are_positions() -> None:
    posts = [_reminder(10, "a"), _reminder(20, "b"), _reminder(30, "c")]
    assert [r.id for r in match_reminders(posts, "#1 и 3")] == [10, 30]
    assert match_reminders(posts, "7") == []


def test_words_match_by_stem() -> None:
    posts = [_reminder(1, "Пятница, обед! " + URL), _reminder(2, "Созвон в 10")]
    assert [r.id for r in match_reminders(posts, "обеды")] == [1]
    assert match_reminders(posts, "кино") == []
