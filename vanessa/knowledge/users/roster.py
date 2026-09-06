"""Canonical nickname roster from ``config/nicknames.yaml``.

Leaf module: index builders resolve telegram ids to People-card slugs without
importing ``vanessa.knowledge.people`` (that package's participants digest
needs ``KnowledgeIndex``, which would close a cycle).
"""

from __future__ import annotations

from functools import lru_cache

from vanessa.infrastructure.ingest.user_backfill import load_nicknames
from vanessa.knowledge.format import slugify
from vanessa.knowledge.users.nicknames import resolve_nicknames_path


@lru_cache
def _nickname_map() -> dict[int, str]:
    return load_nicknames(resolve_nicknames_path())


def canonical_name_for_telegram_id(telegram_id: int | None) -> str | None:
    """Canonical nickname from ``config/nicknames.yaml`` for a telegram id."""
    if telegram_id is None:
        return None
    return _nickname_map().get(telegram_id)


def telegram_id_for_slug(slug: str) -> int | None:
    """Reverse ``config/nicknames.yaml`` lookup: canonical slug -> telegram id."""
    for telegram_id, nickname in _nickname_map().items():
        if slugify(nickname) == slug:
            return telegram_id
    return None
