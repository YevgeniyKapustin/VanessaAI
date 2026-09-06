"""Per-folder ``_index.yaml`` builders for the knowledge vault."""

from __future__ import annotations

import logging
from pathlib import Path

from vanessa.knowledge.format import CULTURE, CULTURE_KINDS, LOGS, slugify
from vanessa.knowledge.schema import VaultNote
from vanessa.knowledge.store.vault import KnowledgeVault
from vanessa.knowledge.users.roster import canonical_name_for_telegram_id

logger = logging.getLogger(__name__)


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _telegram_roster_slug(telegram_id: object) -> str:
    """Canonical People-card slug for a telegram id, from config/nicknames.yaml."""
    try:
        value = int(telegram_id)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    nickname = canonical_name_for_telegram_id(value)
    return slugify(nickname) if nickname else ""


def _assign_telegram_entry(
    people: dict, telegram_id: object, entry: dict, note_id: str
) -> bool:
    """Bind ``telegram_id`` to this card. True means skip the rest of the note."""
    key = str(telegram_id)
    telegram_map = people.setdefault("telegram_id", {})
    existing = telegram_map.get(key)
    if existing is not None and existing.get("id") != note_id:
        roster_slug = _telegram_roster_slug(telegram_id)
        if roster_slug and note_id == roster_slug and existing.get("id") != roster_slug:
            logger.warning(
                "knowledge_index_telegram_reassigned telegram_id=%s from=%s to=%s",
                key,
                existing.get("id"),
                note_id,
            )
            telegram_map[key] = entry
        else:
            logger.warning(
                "knowledge_index_telegram_conflict telegram_id=%s cards=%s,%s preferred=%s",
                key,
                existing.get("id"),
                note_id,
                roster_slug or existing.get("id"),
            )
        return True
    telegram_map[key] = entry
    return False


def _index_alias_keys(people: dict, entry: dict, values: object) -> None:
    aliases = people.setdefault("aliases", {})
    for alias in _as_list(values):
        alias_key = str(alias).strip().lower()
        if alias_key:
            aliases[alias_key] = entry


def build_people_index(notes: list[VaultNote]) -> dict:
    people: dict = {}
    for note in notes:
        rel = note.relative_path
        meta = note.meta
        note_id = str(meta.get("id") or slugify(Path(rel).stem))
        entry = {"id": note_id, "file": rel}
        telegram_id = meta.get("telegram_id")
        if telegram_id is not None and _assign_telegram_entry(
            people, telegram_id, entry, note_id
        ):
            continue
        _index_alias_keys(people, entry, meta.get("aliases"))
        _index_alias_keys(people, entry, meta.get("names"))
    return people


def build_glossary_index(notes: list[VaultNote]) -> dict:
    glossary: dict = {}
    for note in notes:
        rel = note.relative_path
        meta = note.meta
        note_id = str(meta.get("id") or slugify(Path(rel).stem))
        entry = {"id": note_id, "file": rel}
        keys = [*_as_list(meta.get("aliases")), note_id]
        for alias in keys:
            alias_key = str(alias).strip().lower()
            if alias_key:
                glossary.setdefault("aliases", {})[alias_key] = entry
    return {"glossary": glossary}


def build_events_index(notes: list[VaultNote]) -> dict:
    events: list[dict] = []
    for note in notes:
        meta = note.meta
        events.append(
            {
                "id": str(meta.get("id") or slugify(Path(note.relative_path).stem)),
                "file": note.relative_path,
                "date": str(meta.get("date") or ""),
                "title": str(meta.get("title") or ""),
            }
        )
    return {"events": events}


async def build_culture_index(vault: KnowledgeVault) -> dict:
    data: dict = {}
    for kind in CULTURE_KINDS:
        notes = await vault.list_notes(f"{CULTURE}/{kind}")
        items: list[dict] = []
        for note in notes:
            meta = note.meta
            items.append(
                {
                    "id": str(
                        meta.get("id") or slugify(Path(note.relative_path).stem)
                    ),
                    "file": note.relative_path,
                    "title": str(meta.get("title") or ""),
                    "status": str(meta.get("status") or ""),
                }
            )
        if items:
            data[kind] = items
    return data


async def build_logs_index(vault: KnowledgeVault) -> dict:
    logs: dict = {}
    for sub in ("daily", "weekly"):
        notes = await vault.list_notes(f"{LOGS}/{sub}")
        items = [
            {
                "file": note.relative_path,
                "period": str(note.meta.get("period") or sub),
            }
            for note in notes
        ]
        if items:
            logs[sub] = items
    return logs


def build_inbox_index(notes: list[VaultNote]) -> dict:
    return {
        "notes": [
            {
                "file": note.relative_path,
                "type": str(note.meta.get("type") or "note"),
            }
            for note in notes
        ]
    }
