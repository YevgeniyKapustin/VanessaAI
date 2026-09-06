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


def canonical_for_card(meta: dict, roster: dict[int, str]) -> str:
    """Canonical display name for a People card (roster by telegram_id first)."""
    telegram_id = meta.get("telegram_id")
    if telegram_id is not None:
        try:
            roster_name = roster.get(int(telegram_id))
        except (TypeError, ValueError):
            roster_name = None
        if roster_name:
            return str(roster_name)
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
    for field in ("aliases", "names"):
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


def _note_alias_entry(note, roster: dict[int, str]) -> tuple[str, tuple[str, ...]] | None:
    meta = note.meta
    if not isinstance(meta, dict):
        return None
    canonical = canonical_for_card(meta, roster)
    if not canonical:
        return None
    aliases = note_aliases(meta, canonical)
    if not aliases:
        return None
    return canonical, tuple(aliases)


def aliases_from_notes(notes, roster: dict[int, str]) -> dict[str, tuple[str, ...]]:
    if not notes:
        return {}
    result: dict[str, tuple[str, ...]] = {}
    for note in notes:
        entry = _note_alias_entry(note, roster)
        if entry is None:
            continue
        result[entry[0]] = entry[1]
    return result
