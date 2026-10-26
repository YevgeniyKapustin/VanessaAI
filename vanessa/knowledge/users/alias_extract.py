"""Alias extraction from People-card frontmatter."""

from __future__ import annotations

import re

_SPACE_RE = re.compile(r"\s+")


def normalize_alias(text: str) -> str:
    # A leading '@' is stripped so a Telegram username (@nu_ya) and its bare form
    # (nu_ya) normalize to the same key.
    return _SPACE_RE.sub(" ", text.replace("ё", "е").lower().lstrip("@")).strip()


def as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def canonical_for_card(meta: dict) -> str:
    """Canonical display name stored in a People card."""
    return str(meta.get("nickname") or meta.get("id") or "").strip()


def _add_alias(
    aliases: list[str], seen: set[str], alias: str, canonical_key: str
) -> None:
    key = normalize_alias(alias)
    if not key or key in seen or key == canonical_key:
        return
    seen.add(key)
    aliases.append(alias)


def _aliases_from_fields(
    meta: dict, seen: set[str], aliases: list[str], canonical_key: str
) -> None:
    for field in ("aliases", "names", "vrchat_names"):
        for raw in as_list(meta.get(field)):
            _add_alias(aliases, seen, str(raw).strip(), canonical_key)


def _usernames_from_fields(
    meta: dict, seen: set[str], aliases: list[str], canonical_key: str
) -> None:
    for field in ("telegram_username", "username"):
        username = str(meta.get(field) or "").strip()
        if username:
            _add_alias(aliases, seen, username, canonical_key)


def note_aliases(meta: dict, canonical: str) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    canonical_key = normalize_alias(canonical)
    _aliases_from_fields(meta, seen, aliases, canonical_key)
    _usernames_from_fields(meta, seen, aliases, canonical_key)
    return aliases


def _note_alias_entry(note) -> tuple[str, tuple[str, ...]] | None:
    meta = note.meta
    if not isinstance(meta, dict):
        return None
    canonical = canonical_for_card(meta)
    if not canonical:
        return None
    aliases = note_aliases(meta, canonical)
    return canonical, tuple(aliases)


def aliases_from_notes(notes) -> dict[str, tuple[str, ...]]:
    if not notes:
        return {}
    result: dict[str, tuple[str, ...]] = {}
    for note in notes:
        entry = _note_alias_entry(note)
        if entry is None:
            continue
        result[entry[0]] = entry[1]
    return result


def _telegram_nickname_entry(note) -> tuple[int, str] | None:
    if not isinstance(note.meta, dict):
        return None
    try:
        telegram_id = int(note.meta.get("telegram_id"))
    except (TypeError, ValueError):
        return None
    canonical = canonical_for_card(note.meta)
    if telegram_id > 0 and canonical:
        return telegram_id, canonical
    return None


def telegram_nicknames_from_notes(notes) -> dict[int, str]:
    result: dict[int, str] = {}
    for note in notes:
        entry = _telegram_nickname_entry(note)
        if entry is not None:
            result.setdefault(*entry)
    return result
