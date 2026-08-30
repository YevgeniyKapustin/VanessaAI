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
import hashlib
import json
import logging
import re

from vanessa.config.content import AppContent, get_content
from vanessa.config.settings import settings
from vanessa.knowledge.format import PEOPLE, today
from vanessa.knowledge.vault import KnowledgeVault
from vanessa.pipeline.llm.planner.generation_config import LLMGenerationParams
from vanessa.pipeline.llm.providers.protocols import LLMChatCompleter, create_chat_completer

logger = logging.getLogger(__name__)


def _clean_portrait(raw: str) -> str:
    """Trim fences and collapse whitespace/newlines into a short prose block."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    # A portrait is a short prose block: fold newlines into spaces.
    return " ".join(text.split()).strip()


class PortraitPlanner:
    """LLM call that compresses one dossier into a compact portrait."""

    def __init__(
        self,
        content: AppContent | None = None,
        *,
        llm_client: LLMChatCompleter | None = None,
        llm_model: str | None = None,
        generation: LLMGenerationParams | None = None,
    ) -> None:
        self._content = content or get_content()
        self._client = llm_client
        self._model = (
            llm_model
            or settings.knowledge_portrait_model
            or settings.knowledge_model
            or settings.planner_model
        )
        self._generation = generation or LLMGenerationParams(
            temperature=0.2,
            top_p=0.85,
            max_tokens=settings.knowledge_portrait_max_tokens,
        )

    async def portrait(
        self,
        *,
        nickname: str,
        aliases: list[str],
        mood: str,
        dossier: str,
        previous_portrait: str = "",
    ) -> str:
        alias_text = ", ".join(alias for alias in aliases if alias and alias != nickname)
        prompt = self._content.portrait.portrait_prompt.format(
            nickname=nickname,
            aliases=alias_text or nickname,
            mood=mood or "unknown",
            dossier=dossier,
            previous_portrait=(previous_portrait or "").strip() or "(нет)",
        )
        client = self._client or create_chat_completer()
        raw = (
            await client.complete(
                self._model,
                [{"role": "user", "content": prompt}],
                kind="portrait",
                **self._generation.to_llm_kwargs(),
            )
        ).strip()
        return _clean_portrait(raw)


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

    async def run(self, *, force: bool = False) -> int:
        """Regenerate stale portraits. Returns the number of cards updated."""
        if not self._enabled or not self._vault.is_configured:
            return 0
        notes = await self._vault.list_notes(PEOPLE)
        rels = [note.relative_path for note in notes]
        updated = 0
        for rel in rels:
            note = await self._vault.read_note(rel)
            if note is None:
                continue
            try:
                if await self._build_portrait(note, force=force):
                    updated += 1
            except Exception:
                logger.exception("portrait_build_failed path=%s", rel)
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
        meta = dict(note.meta or {})
        signature = self._signature(note)
        if not force and str(meta.get("portrait_signature") or "") == signature:
            return False

        dossier = (note.body or "").strip()
        if not dossier:
            return False
        if len(dossier) > self._max_chars:
            dossier = dossier[: self._max_chars].rstrip() + "\n…"

        nickname = str(meta.get("nickname") or meta.get("id") or note.relative_path)
        mood = str(meta.get("mood") or "").strip()
        aliases = meta.get("aliases")
        alias_list = (
            [str(alias).strip() for alias in aliases if str(alias).strip()]
            if isinstance(aliases, list)
            else []
        )

        portrait = await self._planner.portrait(
            nickname=nickname,
            aliases=alias_list,
            mood=mood,
            dossier=dossier,
            previous_portrait=meta.get("portrait") or "",
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

    @staticmethod
    def _signature(note) -> str:
        """Stable fingerprint of the dossier (body + identity fields)."""
        meta = note.meta or {}
        payload = {
            "body": note.body or "",
            "nickname": str(meta.get("nickname") or ""),
            "mood": str(meta.get("mood") or ""),
            "aliases": meta.get("aliases") or [],
            "telegram_id": meta.get("telegram_id"),
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


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
