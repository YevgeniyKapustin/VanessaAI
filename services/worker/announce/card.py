"""Commits grouped by the product card each one belongs to.

A card is named in the commit title (``[ABC-101] …``, ``ABC-101: …``) or in
the merge branch (``… 'feature/abc-101-…'``); a commit that names none is
«без карточки». The markup that shows this is ``card_render``.
"""

from __future__ import annotations

import html
import re
from collections.abc import Sequence
from dataclasses import dataclass

from services.worker.announce.models import Item

_CARD_PREFIX = re.compile(r"^\s*\[?([A-Z]{2,10}-\d{1,6})\]?")
_CARD_BRANCH = re.compile(r"(?:branch|ветк\w*)\s+'?([^'\s]+)", re.IGNORECASE)
_CARD_IN_TEXT = re.compile(r"\b([A-Za-z]{2,10}-\d{1,6})\b")
_PREFIX_RE = re.compile(r"^\s*\[?[A-Z]{2,10}-\d{1,6}\]?\s*[:—-]?\s*")
_MERGE_RE = re.compile(r"^(?:merge\b|свести\b|merge commit\b)", re.IGNORECASE)
_TOPIC_MAX = 44
_ROWS_MAX = 5
_UNCARDED_MAX = 6


@dataclass(frozen=True, slots=True)
class CardRow:
    """One product card behind the release, as the разбор shows it."""

    card: str
    authors: str
    topic: str
    count: int


def card_key(title: str) -> str:
    """``ABC-101`` when the title names a card, otherwise an empty string.

    A card is named either at the start of the title (``[ABC-101] …``,
    ``ABC-101: …``) or in the merge branch (``… 'feature/abc-101-…'``) —
    any two-or-more-letter key, not one product's naming.
    """
    text = title or ""
    match = _CARD_PREFIX.match(text)
    if match:
        return match.group(1).upper()
    branch = _CARD_BRANCH.search(text)
    if branch:
        inner = _CARD_IN_TEXT.search(branch.group(1))
        if inner:
            return inner.group(1).upper()
    return ""


def topic_of(title: str) -> str:
    """The commit title without its card tag, cut to one table cell."""
    text = _PREFIX_RE.sub("", title or "").strip()
    return text if len(text) <= _TOPIC_MAX else text[: _TOPIC_MAX - 1].rstrip() + "…"


def _groups(items: Sequence[Item]) -> dict[str, list[Item]]:
    """Card id → its commits, in the order the cards first appear."""
    groups: dict[str, list[Item]] = {}
    for item in items:
        key = card_key(item.title)
        if key:
            groups.setdefault(key, []).append(item)
    return groups


def _authors(items: Sequence[Item]) -> str:
    names: list[str] = []
    for item in items:
        name = item.author.strip()
        if name and name not in names:
            names.append(name)
    return ", ".join(names) or "без автора"


def _card_topic(items: Sequence[Item]) -> str:
    """The first real change of the card; a merge title says nothing."""
    for item in items:
        topic = topic_of(item.title)
        if not _MERGE_RE.match(topic):
            return topic
    return "—"


def card_rows(items: Sequence[Item]) -> list[CardRow]:
    """Cards in the order they appear, the biggest first."""
    rows = [
        CardRow(
            card=key,
            authors=_authors(group),
            topic=_card_topic(group),
            count=len(group),
        )
        for key, group in _groups(items).items()
    ]
    rows.sort(key=lambda row: row.count, reverse=True)
    return rows[:_ROWS_MAX]


def uncarded(items: Sequence[Item]) -> list[Item]:
    """Commits that name no card — the ones a plain count hides."""
    return [item for item in items if not card_key(item.title)][:_UNCARDED_MAX]


def escape(text: str) -> str:
    return html.escape(text or "", quote=True)


__all__ = [
    "CardRow",
    "card_key",
    "card_rows",
    "escape",
    "topic_of",
    "uncarded",
]
