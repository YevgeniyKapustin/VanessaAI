"""Telegram-id and alias resolution for person cards."""

from __future__ import annotations

from vanessa.knowledge.format import slugify
from vanessa.knowledge.people.people import canonical_name_for_telegram_id


def person_id_from_alias(people_index: dict, name: str) -> str:
    alias_map = people_index.get("aliases")
    if not isinstance(alias_map, dict):
        return ""
    entry = alias_map.get(name.strip().lower())
    if not isinstance(entry, dict):
        return ""
    person_id = entry.get("id")
    return str(person_id) if person_id else ""


def valid_telegram_id(telegram_id: int | None) -> bool:
    return telegram_id is not None and telegram_id > 0


def id_from_telegram_index(people_index: dict, telegram_id: int) -> str:
    entry = people_index.get("telegram_id", {}).get(str(telegram_id))
    if not isinstance(entry, dict):
        return ""
    person_id = entry.get("id")
    if not person_id:
        return ""
    return str(person_id)


def id_from_display_name(people_index: dict, name: str | None) -> str:
    if not name or not name.strip():
        return ""
    return person_id_from_alias(people_index, name)


def fallback_person_id(people_index: dict, telegram_id: int, name: str | None) -> str:
    nickname = canonical_name_for_telegram_id(telegram_id)
    if nickname:
        return slugify(nickname)
    from_name = id_from_display_name(people_index, name)
    if from_name:
        return from_name
    return f"user-{telegram_id}"
