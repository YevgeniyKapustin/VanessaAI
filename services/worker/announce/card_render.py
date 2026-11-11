"""The same announcement as a rich message: header, bullets, one folded разбор.

What the chat already sees stays visible — the release line and the bullets.
Everything else (which cards the release holds, who wrote them, the rollout
link) folds into ``<details>``, so nobody scrolls a changelog unless they ask
for it. A card id links to its own card when the watch knows the board.
"""

from __future__ import annotations

from collections.abc import Sequence

from services.worker.announce.card import (
    CardRow,
    card_rows,
    escape,
    topic_of,
    uncarded,
)
from services.worker.announce.models import Item

_CARD_SLOT = "{card}"
# Russian pluralia: 1 / 2–4 / the rest, with 11–14 always in «the rest».
_ONE = 1
_FEW_MIN = 2
_FEW_MAX = 4
_TEEN_ELEVEN = 11
_TEENS_MIN = 12
_TEENS_MAX = 14
_TEN = 10
_HUNDRED = 100


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


def card_anchor(template: str, card: str) -> str:
    """The card id as a link to its own card, when a ``{card}`` template is set.

    ``https://<board>/<workspace>/browse/{card}/`` + ``ABC-101`` is one card
    page; an empty template keeps the id as plain text.
    """
    url = template.replace(_CARD_SLOT, card).strip() if template else ""
    if not url:
        return escape(card)
    return f'<a href="{escape(url)}">{escape(card)}</a>'


def _table(rows: Sequence[CardRow], card_url: str = "") -> list[str]:
    if not rows:
        return []
    head = "<tr><th>Карточка</th><th>Автор</th><th>О чём</th></tr>"
    body = "".join(
        f"<tr><td>{card_anchor(card_url, row.card)}</td>"
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
    card_url: str = "",
) -> str:
    """The message as rich HTML: visible summary, folded разбор, footer."""
    rows = card_rows(items)
    parts = _visible(header_html, bullets)
    summary = (
        f"разбор: {total} {_plural(total, 'коммит', 'коммита', 'коммитов')}, "
        f"{len(rows)} {_plural(len(rows), 'карточка', 'карточки', 'карточек')}"
    )
    folded = [f"<details><summary>{escape(summary)}</summary>"]
    folded += _table(rows, card_url)
    folded += _rest(uncarded(items))
    if footer_html:
        folded.append(f"<p>{footer_html}</p>")
    folded.append("</details>")
    return "".join(parts + folded)


__all__ = ["build_card", "card_anchor"]
