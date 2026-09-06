"""PortraitBuilder: hierarchical dossier summarization.

Each People card accumulates fine-grained facts over time — often 100+ lines of
trivia like «ел пирог с луком». Dumping the whole card into the compose prompt
bloats the context and dulls the model's attention.

This module runs an LLM that compresses every dossier into a compact 3-5 sentence
"portrait" stored in the card's frontmatter (``portrait``), alongside a
``portrait_signature`` fingerprint of the dossier, so a portrait is only
regenerated when the dossier actually changed. The compose path then injects the
compact portrait for background context and falls back to the raw (bounded)
dossier only when a concrete fact is asked (see ``KnowledgeRetriever``).
"""

from __future__ import annotations

import asyncio
import logging

from vanessa.config.content import get_content
from vanessa.config.settings import settings
from vanessa.knowledge.format import PEOPLE, today
from vanessa.knowledge.portraits.portrait_fields import (
    clip_dossier,
    dossier_signature,
    note_meta,
    portrait_is_current,
    portrait_prompt_fields,
)
from vanessa.knowledge.portraits.portrait_planner import PortraitPlanner
from vanessa.knowledge.store.vault import KnowledgeVault

__all__ = ["PortraitBuilder", "PortraitPlanner", "PortraitWorker"]

logger = logging.getLogger(__name__)


class PortraitBuilder:
    """Scan the People folder and regenerate stale portraits.

    A portrait is stale when the card has no ``portrait`` yet, or when the
    dossier changed since the last generation (fingerprinted in
    ``portrait_signature``). Regeneration is fail-open per person.
    """

    def __init__(
        self,
        vault: KnowledgeVault,
        planner: PortraitPlanner | None = None,
        *,
        enabled: bool | None = None,
        max_chars: int | None = None,
    ) -> None:
        self._vault = vault
        self._planner = planner or PortraitPlanner()
        self._enabled = (
            enabled
            if enabled is not None
            else (settings.knowledge_portrait_enabled and get_content().portrait.enabled)
        )
        self._max_chars = (
            max_chars if max_chars is not None else settings.knowledge_portrait_max_chars
        )

    async def _refresh_one(self, rel: str, *, force: bool) -> int:
        note = await self._vault.read_note(rel)
        if note is None:
            return 0
        try:
            if await self._build_portrait(note, force=force):
                return 1
        except Exception:
            logger.exception("portrait_build_failed path=%s", rel)
        return 0

    async def run(self, *, force: bool = False) -> int:
        """Regenerate stale portraits. Returns the number of cards updated."""
        if not self._enabled or not self._vault.is_configured:
            return 0
        rels = [note.relative_path for note in await self._vault.list_notes(PEOPLE)]
        updated = 0
        for rel in rels:
            updated += await self._refresh_one(rel, force=force)
        logger.info(
            "portrait_build_done scanned=%s updated=%s force=%s",
            len(rels),
            updated,
            force,
        )
        return updated

    def _people_notes(self) -> list[str]:
        return [note.relative_path for note in self._vault.list_notes_sync(PEOPLE)]

    async def _build_portrait(self, note, *, force: bool) -> bool:
        meta = note_meta(note)
        signature = dossier_signature(note)
        if portrait_is_current(meta, signature, force=force):
            return False

        dossier = clip_dossier(note.body, self._max_chars)
        if not dossier:
            return False

        nickname, alias_list, mood, previous = portrait_prompt_fields(
            meta, note.relative_path
        )
        portrait = await self._planner.portrait(
            nickname=nickname,
            aliases=alias_list,
            mood=mood,
            dossier=dossier,
            previous_portrait=previous,
        )
        if not portrait:
            return False

        meta["portrait"] = portrait
        meta["portrait_signature"] = signature
        meta["portrait_updated"] = today()
        await self._vault.write_note(
            note.relative_path,
            meta,
            note.body or "",
            mutation_source="portrait",
        )
        logger.info(
            "portrait_written path=%s portrait_len=%s",
            note.relative_path,
            len(portrait),
        )
        return True


class PortraitWorker:
    """Background loop that periodically refreshes stale person portraits."""

    def __init__(
        self,
        builder: PortraitBuilder,
        *,
        poll_seconds: int = 300,
    ) -> None:
        self._builder = builder
        self._poll = max(1, poll_seconds)

    async def run_forever(self) -> None:
        while True:
            try:
                updated = await self._builder.run()
                if updated:
                    logger.info("portrait_worker_cycle updated=%s", updated)
            except Exception:
                logger.exception("portrait_worker_cycle_failed")
            await asyncio.sleep(self._poll)
