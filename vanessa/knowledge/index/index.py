"""Folder index manifests (_index.yaml): load, cache, rebuild per folder type.

The bot never scans the whole vault to find something: every folder keeps a
machine ``_index.yaml`` with alias maps and entry lists, and retrieval resolves
nicknames/terms to files in O(1) through these manifests.
"""

from __future__ import annotations

import asyncio
import logging

from vanessa.knowledge.format import (
    CULTURE,
    INBOX,
    INDEX_FILENAME,
    LOGS,
    LOGS_DAILY,
    LOGS_WEEKLY,
    LORE_EVENTS,
    LORE_GLOSSARY,
    PEOPLE,
)
from vanessa.knowledge.index.index_build import (
    build_culture_index,
    build_events_index,
    build_glossary_index,
    build_inbox_index,
    build_logs_index,
    build_people_index,
)
from vanessa.knowledge.store.vault import KnowledgeVault

logger = logging.getLogger(__name__)


async def _people_manifest(vault: KnowledgeVault) -> dict:
    return build_people_index(await vault.list_notes(PEOPLE))


async def _glossary_manifest(vault: KnowledgeVault) -> dict:
    return build_glossary_index(await vault.list_notes(LORE_GLOSSARY))


async def _events_manifest(vault: KnowledgeVault) -> dict:
    return build_events_index(await vault.list_notes(LORE_EVENTS))


async def _inbox_manifest(vault: KnowledgeVault) -> dict:
    return build_inbox_index(await vault.list_notes(INBOX))


_MANIFEST_BUILDERS = {
    PEOPLE: _people_manifest,
    LORE_GLOSSARY: _glossary_manifest,
    LORE_EVENTS: _events_manifest,
    CULTURE: build_culture_index,
    LOGS: build_logs_index,
    LOGS_DAILY: build_logs_index,
    LOGS_WEEKLY: build_logs_index,
    INBOX: _inbox_manifest,
}


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

    async def _manifest_for(self, folder: str) -> dict:
        builder = _MANIFEST_BUILDERS.get(folder)
        if builder is None:
            return {}
        return await builder(self._vault)

    async def rebuild_folder(self, folder: str) -> dict:
        if not self._vault.is_configured:
            return {}
        async with self._lock:
            data = await self._manifest_for(folder)
            key = self._index_path(folder)
            await self._vault.write_yaml(key, data)
            self._cache[key] = data
            self._mtime[key] = await self._vault.notes_signature(folder)
            logger.info("knowledge_index_rebuilt folder=%s", folder)
            return data
