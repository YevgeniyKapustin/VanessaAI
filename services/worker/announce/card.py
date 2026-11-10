"""The same announcement as a rich message: header, bullets, one folded разбор.

What the chat already sees stays visible — the release line and the bullets.
Everything else (which cards the release holds, who wrote them, the rollout
link) folds into ``<details>``, so nobody scrolls a changelog unless they ask
for it. Cards are grouped by the issue id in the commit title (``[ABC-101] …``).
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
# Russian pluralia: 1 / 2–4 / the rest, with 11–14 always in «the rest».
_ONE = 1
_FEW_MIN = 2
_FEW_MAX = 4
_TEEN_ELEVEN = 11
_TEENS_MIN = 12
_TEENS_MAX = 14
_TEN = 10
_HUNDRED = 100


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


def _plural(count: int, one: str, few: str, many: str) -> str:
    tail = count % _TEN
    hundred = count % _HUNDRED
    if tail == _ONE and hundred != _TEEN_ELEVEN:
        return one
    if _FEW_MIN <= tail <= _FEW_MAX and not _TEENS_MIN <= hundred <= _TEENS_MAX:
        return few
    return many


def _visible(header_html: str, bullets: Sequence[str]) -> list[str]:
    parts = [f"<p>{header_html}</p>"] if header_html else []
    parts.extend(f"<p>{escape(bullet)}</p>" for bullet in bullets if bullet.strip())
    return parts


def _table(rows: Sequence[CardRow]) -> list[str]:
    if not rows:
        return []
    head = "<tr><th>Карточка</th><th>Автор</th><th>О чём</th></tr>"
    body = "".join(
        f"<tr><td>{escape(row.card)}</td>"
        f"<td>{escape(row.authors)} · {row.count}</td>"
        f"<td>{escape(row.topic)}</td></tr>"
        for row in rows
    )
    return [f"<table>{head}{body}</table>"]


def _rest(items: Sequence[Item]) -> list[str]:
    if not items:
        return []
    line = "<p>Остальные коммиты выпуска — без карточки:</p>"
    entries = "".join(
        f"<li>{escape(topic_of(item.title))}"
        + (f" — {escape(item.author)}" if item.author.strip() else "")
        + "</li>"
        for item in items
    )
    return [line, f"<ul>{entries}</ul>"]


def build_card(
    *,
    header_html: str,
    bullets: Sequence[str],
    items: Sequence[Item],
    total: int,
    footer_html: str = "",
) -> str:
    """The message as rich HTML: visible summary, folded разбор, footer."""
    rows = card_rows(items)
    parts = _visible(header_html, bullets)
    summary = (
        f"разбор: {total} {_plural(total, 'коммит', 'коммита', 'коммитов')}, "
        f"{len(rows)} {_plural(len(rows), 'карточка', 'карточки', 'карточек')}"
    )
    folded = [f"<details><summary>{escape(summary)}</summary>"]
    folded += _table(rows)
    folded += _rest(uncarded(items))
    if footer_html:
        folded.append(f"<p>{footer_html}</p>")
    folded.append("</details>")
    return "".join(parts + folded)


__all__ = [
    "CardRow",
    "build_card",
    "card_key",
    "card_rows",
    "escape",
    "topic_of",
    "uncarded",
]
