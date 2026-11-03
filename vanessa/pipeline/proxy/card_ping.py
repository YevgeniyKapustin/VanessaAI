"""A bot's card ping is a work question: force the work lookup.

«Фон спринта: ABC-123 … без движения. Двигай или скажи, что мешает» is
not small talk: the answer is the card's real state, which only a work lookup
has. The planner usually sees that, but a missed flag costs the whole answer,
so a card id in a proxy question guarantees the lookup and keeps the id.
"""

from __future__ import annotations

import re
from dataclasses import replace

from vanessa.config.settings import settings
from vanessa.pipeline.decision.turn_plan import TurnPlan

#: Work card ids in the chats: ABC-123, VAN-12, OPS-7.
_CARD_RE = re.compile(r"(?<![\w-])[A-Z][A-Z0-9]{1,9}-\d{1,6}(?![\w-])")
_STATUS_TAIL = (
    "\n\nНужен фактический статус по этой карточке: что уже сделано, "
    "что осталось и что мешает."
)


def card_ids(text: str) -> tuple[str, ...]:
    """Card ids named in the message, in order, without duplicates."""
    seen: list[str] = []
    for match in _CARD_RE.findall(text or ""):
        if match not in seen:
            seen.append(match)
    return tuple(seen)


def _query(message: str, ids: tuple[str, ...]) -> str:
    text = message.strip()
    if not any(card in text for card in ids):
        text = f"{' '.join(ids)}: {text}"
    limit = settings.hermes_query_max_chars
    return (text[: max(0, limit - len(_STATUS_TAIL))] + _STATUS_TAIL).strip()


def apply_proxy_card_lookup(
    plan: TurnPlan, message: str, *, proxy_question: bool
) -> TurnPlan:
    """Guarantee a work lookup when an agent pings the owner about a card."""
    if not proxy_question:
        return plan
    ids = card_ids(message)
    if not ids:
        return plan
    if plan.ask_hermes and all(card in plan.hermes_query for card in ids):
        return plan
    return replace(plan, ask_hermes=True, hermes_query=_query(message, ids))


__all__ = ["apply_proxy_card_lookup", "card_ids"]
