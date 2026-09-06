"""Exact alias/token fetch over vault folder indexes."""

from __future__ import annotations

import logging
import re

from vanessa.knowledge.format import (
    CULTURE,
    LOGS,
    LORE_EVENTS,
    LORE_GLOSSARY,
    PEOPLE,
)
from vanessa.knowledge.schema import KnowledgeBlock

logger = logging.getLogger("vanessa.knowledge.retriever")

_TOKEN = re.compile(r"[a-zа-яё]{3,}", re.IGNORECASE)


def _fetch_indexes(
    knowledge_indexes: tuple[str, ...], humor_query: str, *, humor_ok: bool
) -> set[str]:
    indexes = set(knowledge_indexes)
    if humor_ok and humor_query.strip():
        indexes.add("lore")
    return indexes


def _fetch_query(knowledge_query: str, user_message: str) -> str:
    return (knowledge_query or user_message or "").strip()


class RetrieverFetchMixin:
    async def _maybe_people(
        self,
        indexes: set[str],
        query: str,
        *,
        people_detail: bool,
        people_files: list[str] | None,
    ) -> list[KnowledgeBlock]:
        if "people" not in indexes:
            return []
        return await self._people_blocks(
            query, detail=people_detail, people_files=people_files
        )

    async def _maybe_lore(
        self, indexes: set[str], query: str, humor_query: str
    ) -> list[KnowledgeBlock]:
        if "lore" not in indexes:
            return []
        return await self._fetch_lore(query or humor_query or "")

    async def _maybe_culture(
        self, indexes: set[str], query: str
    ) -> list[KnowledgeBlock]:
        if "culture" not in indexes:
            return []
        return await self._fetch_culture(query)

    async def _maybe_logs(self, indexes: set[str]) -> list[KnowledgeBlock]:
        if "logs" not in indexes:
            return []
        return await self._fetch_logs()

    async def fetch(
        self,
        *,
        knowledge_indexes: tuple[str, ...] = (),
        knowledge_query: str = "",
        humor_ok: bool = False,
        humor_query: str = "",
        user_message: str = "",
        people_detail: bool = False,
        people_files: list[str] | None = None,
    ) -> list[KnowledgeBlock]:
        if not self._vault.is_configured:
            return []
        indexes = _fetch_indexes(
            knowledge_indexes, humor_query, humor_ok=humor_ok
        )
        if not indexes:
            return []

        query = _fetch_query(knowledge_query, user_message)
        blocks: list[KnowledgeBlock] = []
        blocks.extend(
            await self._maybe_people(
                indexes, query, people_detail=people_detail, people_files=people_files
            )
        )
        blocks.extend(await self._maybe_lore(indexes, query, humor_query))
        blocks.extend(await self._maybe_culture(indexes, query))
        blocks.extend(await self._maybe_logs(indexes))

        blocks = self._dedupe(blocks)
        logger.info(
            "knowledge_fetch indexes=%s query=%r blocks=%s",
            sorted(indexes),
            query,
            len(blocks),
        )
        return blocks[: self._detail_cap(detail=people_detail)]

    async def _people_blocks(
        self,
        query: str,
        *,
        detail: bool,
        people_files: list[str] | None,
    ) -> list[KnowledgeBlock]:
        if not people_files:
            return await self._fetch_people(query, detail=detail)
        people_index = await self._index.load_folder(PEOPLE)
        raw_aliases = (
            people_index.get("aliases") if isinstance(people_index, dict) else None
        )
        people_aliases = raw_aliases if isinstance(raw_aliases, dict) else {}
        target_files = self._filter_self_cards(
            people_files,
            self._self_card_paths(people_aliases),
        )
        entries = [{"file": path} for path in target_files]
        return await self._read_blocks(
            entries[: self._people_max_blocks],
            detail=detail,
        )

    async def _fetch_people(self, query: str, *, detail: bool = False) -> list[KnowledgeBlock]:
        people_index = await self._index.load_folder(PEOPLE)
        aliases = people_index.get("aliases", {})
        hits = self._match_aliases(aliases, query, limit=self._people_max_blocks)
        return await self._read_blocks(hits, detail=detail)

    async def _fetch_lore(self, query: str) -> list[KnowledgeBlock]:
        glossary = (await self._index.load_folder(LORE_GLOSSARY)).get("glossary", {})
        aliases = glossary.get("aliases", {})
        hits = self._match_aliases(aliases, query)

        events = (await self._index.load_folder(LORE_EVENTS)).get("events", [])
        query_tokens = {t.lower() for t in _TOKEN.findall(query.lower())}
        for event in events:
            title = str(event.get("title") or "")
            title_tokens = {t.lower() for t in _TOKEN.findall(title.lower())}
            if query_tokens and (query_tokens & title_tokens):
                hits.append(event)
        return await self._read_blocks(hits)

    async def _fetch_culture(self, query: str) -> list[KnowledgeBlock]:
        culture = await self._index.load_folder(CULTURE)
        query_tokens = {t.lower() for t in _TOKEN.findall(query.lower())}
        hits: list[dict] = []
        for kind, items in culture.items():
            kind_match = kind in query_tokens
            for item in items:
                title = str(item.get("title") or "")
                title_tokens = {t.lower() for t in _TOKEN.findall(title.lower())}
                if not query or kind_match or (query_tokens & title_tokens):
                    hits.append(item)
        return await self._read_blocks(hits)

    async def _fetch_logs(self) -> list[KnowledgeBlock]:
        logs = await self._index.load_folder(LOGS)
        hits: list[dict] = []
        for sub in ("weekly", "daily"):
            entries = list(logs.get(sub, []))
            entries.sort(key=lambda item: str(item.get("file") or ""), reverse=True)
            hits.extend(entries)
        return await self._read_blocks(hits)
