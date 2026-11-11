"""Glue between a composed announcement and the rich card Telegram draws.

The card markup itself lives in ``card``; this module only turns the pieces
compose already has (header, bullets, footer) into that markup, and refuses
to ship a card whose markup would be cut by the wire cap.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from services.worker.announce.card import escape
from services.worker.announce.card_render import build_card
from services.worker.announce.models import Item
from vanessa.contracts.outbound import RICH_HTML_MAX_CHARS

_MD_LINK = re.compile(r"\[([^\[\]]+)\]\(([^)\s]+)\)")


def links_to_html(text: str) -> str:
    """Markdown links become anchors; every other character is escaped."""
    escaped = escape(text)
    return _MD_LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', escaped)


def card_for(
    *,
    header: str,
    bullets: Sequence[str],
    items: Sequence[Item],
    total: int,
    footer: str = "",
    card_url: str = "",
    limit: int = RICH_HTML_MAX_CHARS,
) -> str | None:
    """The folded card for these parts; None when the markup would be cut."""
    markup = build_card(
        header_html=links_to_html(header),
        bullets=bullets,
        items=items,
        total=total,
        footer_html=links_to_html(footer) if footer else "",
        card_url=card_url,
    )
    # Cut markup never parses: an oversized card is dropped, the text stays.
    return markup if len(markup) <= limit else None


__all__ = ["card_for", "links_to_html"]
