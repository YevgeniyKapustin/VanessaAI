"""Pick which scheduled posts a cancel request means."""

from __future__ import annotations

import re

from vanessa.core.reminders import Reminder

ALL_TARGETS = frozenset({"all", "*", "все", "всё", "всех", "всё подряд"})
_NUMBERS_RE = re.compile(r"[\s,#№и]*\d[\d\s,#№и]*")
_WORD_RE = re.compile(r"[\w.-]+")
_MIN_WORD = 4
_STEM_KEEP = 5
_DROP_ENDING_FROM = 5


def stem(word: str) -> str:
    """Crude Russian-friendly stem: «обеды» → «обед», «напоминалку» → «напом»."""
    if len(word) > _STEM_KEEP:
        return word[:_STEM_KEEP]
    if len(word) >= _DROP_ENDING_FROM:
        return word[:-1]
    return word


def _by_position(reminders: list[Reminder], target: str) -> list[Reminder]:
    positions = {int(num) for num in re.findall(r"\d+", target)}
    return [r for index, r in enumerate(reminders, start=1) if index in positions]


def _by_words(reminders: list[Reminder], target: str) -> list[Reminder]:
    words = [w for w in _WORD_RE.findall(target.lower()) if len(w) >= _MIN_WORD]
    stems = {stem(word) for word in words}
    return [r for r in reminders if any(s in r.text.lower() for s in stems)]


def _only_one(reminders: list[Reminder]) -> list[Reminder] | None:
    return list(reminders) if len(reminders) == 1 else None


def match_reminders(reminders: list[Reminder], target: str) -> list[Reminder] | None:
    """Matching posts; None when the target is empty and several posts exist.

    Numbers are 1-based positions in the chat list (the order she lists them).
    """
    target = target.strip().lower()
    if not target:
        return _only_one(reminders)
    if target in ALL_TARGETS:
        return list(reminders)
    if _NUMBERS_RE.fullmatch(target):
        return _by_position(reminders, target)
    return _by_words(reminders, target)


__all__ = ["ALL_TARGETS", "match_reminders", "stem"]
