"""Canonical nickname roster from People cards.

Leaf module: index builders resolve telegram ids to People-card slugs without
importing ``vanessa.knowledge.people`` (that package's participants digest
needs ``KnowledgeIndex``, which would close a cycle).
"""

from __future__ import annotations

from vanessa.knowledge.format import slugify
from vanessa.knowledge.users.nicknames import get_telegram_nicknames


def canonical_name_for_telegram_id(telegram_id: int | None) -> str | None:
    """Canonical nickname from the People card for a Telegram ID."""
    if telegram_id is None:
        return None
    return get_telegram_nicknames().get(telegram_id)


def telegram_id_for_slug(slug: str) -> int | None:
    """Resolve a canonical nickname slug to its People-card Telegram ID."""
    for telegram_id, nickname in get_telegram_nicknames().items():
        if slugify(nickname) == slug:
            return telegram_id
    return None
