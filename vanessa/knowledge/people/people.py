"""Canonical person identity resolution for the knowledge vault.

The memory-planner LLM returns free-form ``person`` references (nicknames,
first names, chat handles). Those must collapse onto ONE stable person card,
otherwise the same participant gets several dossiers (e.g. «капуста»,
«капуст» and «Евгений» for the same person).

Sources of truth, in order:

1. The ``People/_index.yaml`` manifest — existing cards with their
   ``id`` / ``aliases`` / ``telegram_id``.
2. Cached People-card metadata — canonical names and Telegram IDs.

The writer resolves every update's ``person`` through :func:`canonicalize_person`
before choosing the card file, so duplicate spellings never create new cards.
"""

from __future__ import annotations

import logging

from vanessa.knowledge.format import slugify
from vanessa.knowledge.people.people_identity import (
    identity_key,
    identity_similar,
    identity_tokens,
    levenshtein,
    name_variants,
    normalize_person_text,
)
from vanessa.knowledge.users.nicknames import get_chat_nicknames
from vanessa.knowledge.users.roster import (
    canonical_name_for_telegram_id,
    telegram_id_for_slug,
)

logger = logging.getLogger(__name__)

__all__ = [
    "canonical_name_for_telegram_id",
    "canonicalize_person",
    "identity_key",
    "identity_similar",
    "identity_tokens",
    "levenshtein",
    "telegram_id_for_slug",
]


def _entry_id(value: object) -> str:
    """Extract the ``id`` from an index entry dict, or an empty string."""
    if isinstance(value, dict):
        note_id = value.get("id")
        if note_id is not None:
            return str(note_id)
    return ""


def _id_from_telegram(
    telegram_id: int | None,
    telegram_map: dict,
    normalized_telegrams: dict,
    reference: str,
) -> str:
    if telegram_id is not None:
        card_id = _entry_id(telegram_map.get(str(telegram_id)))
        if card_id:
            return card_id
    if reference.isdigit():
        return _entry_id(normalized_telegrams.get(reference))
    return ""


def _variant_map(normalized_aliases: dict) -> dict[str, str]:
    variant_to_entry: dict[str, str] = {}
    for alias, entry in normalized_aliases.items():
        entry_id = _entry_id(entry)
        if not entry_id:
            continue
        for variant in name_variants(alias):
            variant_to_entry.setdefault(variant, entry_id)
    return variant_to_entry


def _first_mapped(keys: list[str], variant_to_entry: dict[str, str]) -> str:
    for key in keys:
        card_id = variant_to_entry.get(key) or ""
        if card_id:
            return card_id
    return ""


def _id_from_alias_fuzzy(reference: str, normalized_aliases: dict) -> str:
    variant_to_entry = _variant_map(normalized_aliases)
    return _first_mapped([reference, *name_variants(reference)], variant_to_entry)


def _id_from_identity(reference: str, normalized_aliases: dict) -> str:
    reference_key = identity_key(reference)
    for alias, entry in normalized_aliases.items():
        entry_id = _entry_id(entry)
        if not entry_id:
            continue
        if identity_key(alias) == reference_key or identity_similar(reference, alias):
            return entry_id
    return ""


def _roster_nickname_matches(
    reference: str, nickname: str, reference_key: str
) -> bool:
    normalized_nickname = normalize_person_text(nickname)
    if normalized_nickname == reference:
        return True
    if reference in name_variants(normalized_nickname):
        return True
    if identity_key(nickname) == reference_key:
        return True
    return identity_similar(reference, nickname)


def _id_from_roster(reference: str) -> str:
    reference_key = identity_key(reference)
    for nickname in get_chat_nicknames():
        if _roster_nickname_matches(reference, nickname, reference_key):
            return slugify(nickname)
    return ""


def canonicalize_person(
    person: str,
    telegram_id: int | None,
    people_index: dict | None,
) -> str:
    """Map a free-form person reference to a stable person-card id.

    Resolution order:

    1. ``telegram_id`` -> existing People card (index ``telegram_id`` map).
    2. name / alias / id -> existing People card (index ``aliases`` map),
       trying the exact reference, then fuzzy variants (no parentheticals,
       stem before ``(``) on both the reference and the alias keys.
    3. canonical nickname from cached People-card metadata.
    4. fallback: slugify the reference (a brand-new card).

    Returns an empty string when the reference is blank.
    """
    reference = normalize_person_text(person)
    if not reference:
        return ""
    index = people_index or {}
    alias_map = index.get("aliases")
    telegram_map = index.get("telegram_id")
    alias_map = alias_map if isinstance(alias_map, dict) else {}
    telegram_map = telegram_map if isinstance(telegram_map, dict) else {}
    normalized_aliases = {
        normalize_person_text(str(key)): entry for key, entry in alias_map.items()
    }
    normalized_telegrams = {str(key): entry for key, entry in telegram_map.items()}

    resolvers = (
        lambda: _id_from_telegram(
            telegram_id, telegram_map, normalized_telegrams, reference
        ),
        lambda: _entry_id(normalized_aliases.get(reference)),
        lambda: _id_from_alias_fuzzy(reference, normalized_aliases),
        lambda: _id_from_identity(reference, normalized_aliases),
        lambda: _id_from_roster(reference),
    )
    for resolve in resolvers:
        card_id = resolve()
        if card_id:
            return card_id

    # Fallback: treat the reference as a brand-new person. A new card is an
    # anomaly (every chat participant has a canonical nickname), so log it.
    logger.warning(
        "knowledge_new_person_card created=%s reference=%r telegram_id=%s",
        slugify(person),
        person,
        telegram_id,
    )
    return slugify(person)
