"""Folder index manifests (_index.yaml): load, cache, rebuild per folder type.

The bot never scans the whole vault to find something: every folder keeps a
machine ``_index.yaml`` with alias maps and entry lists, and retrieval resolves
nicknames/terms to files in O(1) through these manifests.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from vanessa.knowledge.format import (
    CULTURE,
    CULTURE_KINDS,
    INBOX,
    INDEX_FILENAME,
    LOGS,
    LOGS_DAILY,
    LOGS_WEEKLY,
    LORE_EVENTS,
    LORE_GLOSSARY,
    PEOPLE,
    slugify,
)
from vanessa.knowledge.people import canonical_name_for_telegram_id
from vanessa.knowledge.schema import VaultNote
from vanessa.knowledge.vault import KnowledgeVault

logger = logging.getLogger(__name__)


def _telegram_roster_slug(telegram_id: object) -> str:
    """Canonical People-card slug for a telegram id, from config/nicknames.yaml."""
    try:
        value = int(telegram_id)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    nickname = canonical_name_for_telegram_id(value)
    return slugify(nickname) if nickname else ""


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


class KnowledgeIndex:
    """Loads and rebuilds per-folder ``_index.yaml`` manifests."""

    def __init__(self, vault: KnowledgeVault) -> None:
        self._vault = vault
        self._cache: dict[str, dict] = {}
        self._mtime: dict[str, tuple] = {}
        self._lock = asyncio.Lock()

    def _index_path(self, folder: str) -> str:
        return f"{folder}/{INDEX_FILENAME}"

    async def load_folder(self, folder: str) -> dict:
        if not self._vault.is_configured:
            return {}
        async with self._lock:
            key = self._index_path(folder)
            signature = await self._vault.notes_signature(folder)
            if key in self._cache and self._mtime.get(key) == signature:
                return self._cache[key]
            data = await self._vault.read_yaml(key)
            if not isinstance(data, dict):
                data = {}
            self._cache[key] = data
            self._mtime[key] = signature
            return data

    async def rebuild_folder(self, folder: str) -> dict:
        if not self._vault.is_configured:
            return {}
        async with self._lock:
            if folder == PEOPLE:
                notes = await self._vault.list_notes(PEOPLE)
                data = self._build_people_index(notes)
            elif folder == LORE_GLOSSARY:
                notes = await self._vault.list_notes(LORE_GLOSSARY)
                data = self._build_glossary_index(notes)
            elif folder == LORE_EVENTS:
                notes = await self._vault.list_notes(LORE_EVENTS)
                data = self._build_events_index(notes)
            elif folder == CULTURE:
                data = await self._build_culture_index()
            elif folder in (LOGS, LOGS_DAILY, LOGS_WEEKLY):
                data = await self._build_logs_index()
            elif folder == INBOX:
                notes = await self._vault.list_notes(INBOX)
                data = self._build_inbox_index(notes)
            else:
                data = {}
            key = self._index_path(folder)
            await self._vault.write_yaml(key, data)
            self._cache[key] = data
            self._mtime[key] = await self._vault.notes_signature(folder)
            logger.info("knowledge_index_rebuilt folder=%s", folder)
            return data

    def _build_people_index(self, notes: list[VaultNote]) -> dict:
        people: dict = {}
        for note in notes:
            rel = note.relative_path
            meta = note.meta
            note_id = str(meta.get("id") or slugify(Path(rel).stem))
            entry = {"id": note_id, "file": rel}
            telegram_id = meta.get("telegram_id")
            if telegram_id is not None:
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
                    continue
                telegram_map[key] = entry
            for alias in _as_list(meta.get("aliases")):
                alias_key = str(alias).strip().lower()
                if alias_key:
                    people.setdefault("aliases", {})[alias_key] = entry
            for name in _as_list(meta.get("names")):
                name_key = str(name).strip().lower()
                if name_key:
                    people.setdefault("aliases", {})[name_key] = entry
        return people

    def _build_glossary_index(self, notes: list[VaultNote]) -> dict:
        glossary: dict = {}
        for note in notes:
            rel = note.relative_path
            meta = note.meta
            note_id = str(meta.get("id") or slugify(Path(rel).stem))
            entry = {"id": note_id, "file": rel}
            keys = list(_as_list(meta.get("aliases"))) + [note_id]
            for alias in keys:
                alias_key = str(alias).strip().lower()
                if alias_key:
                    glossary.setdefault("aliases", {})[alias_key] = entry
        return {"glossary": glossary}

    def _build_events_index(self, notes: list[VaultNote]) -> dict:
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

    async def _build_culture_index(self) -> dict:
        data: dict = {}
        for kind in CULTURE_KINDS:
            notes = await self._vault.list_notes(f"{CULTURE}/{kind}")
            items: list[dict] = []
            for note in notes:
                meta = note.meta
                items.append(
                    {
                        "id": str(meta.get("id") or slugify(Path(note.relative_path).stem)),
                        "file": note.relative_path,
                        "title": str(meta.get("title") or ""),
                        "status": str(meta.get("status") or ""),
                    }
                )
            if items:
                data[kind] = items
        return data

    async def _build_logs_index(self) -> dict:
        logs: dict = {}
        for sub in ("daily", "weekly"):
            notes = await self._vault.list_notes(f"{LOGS}/{sub}")
            items = [
                {"file": note.relative_path, "period": str(note.meta.get("period") or sub)}
                for note in notes
            ]
            if items:
                logs[sub] = items
        return logs

    def _build_inbox_index(self, notes: list[VaultNote]) -> dict:
        return {
            "notes": [
                {"file": note.relative_path, "type": str(note.meta.get("type") or "note")}
                for note in notes
            ]
        }
