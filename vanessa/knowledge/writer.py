"""KnowledgeVaultWriter: apply MemoryPlan updates with merge semantics.

Each update targets a stable file (person card, glossary entry, culture
recommendation) or an append-only dated file (events, weekly logs). Merges are
idempotent: quote/fact lines are deduped and ``source_message_ids`` accumulate,
so the post-reply stage and the periodic sweep never duplicate content.
"""

from __future__ import annotations

import logging
from datetime import datetime

from vanessa.knowledge.format import (
    CULTURE,
    LOGS,
    LOGS_WEEKLY,
    LORE_EVENTS,
    LORE_GLOSSARY,
    PEOPLE,
    TYPE_EVENT,
    TYPE_GLOSSARY,
    TYPE_LOG,
    TYPE_PERSON,
    TYPE_RECOMMENDATION,
    culture_kind_folder,
    slugify,
    today,
)
from vanessa.knowledge.index import KnowledgeIndex
from vanessa.knowledge.people import canonicalize_person, telegram_id_for_slug
from vanessa.knowledge.schema import MemoryPlan, VaultNote
from vanessa.knowledge.vault import KnowledgeVault
from vanessa.knowledge.vector_index import KnowledgeVectorIndexer

logger = logging.getLogger(__name__)


def _attach_telegram_id(meta: dict, telegram_id: object, person_id: str) -> None:
    """Attach a ``telegram_id`` to a person card when known.

    Prefers an explicit ``telegram_id`` from the LLM update; otherwise derives
    it from the canonical nickname roster when the resolved card matches one.
    """
    if telegram_id is not None:
        meta["telegram_id"] = telegram_id
        return
    known = telegram_id_for_slug(person_id)
    if known is not None:
        meta["telegram_id"] = known


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _append_to_section(body: str, heading: str, new_lines: list[str]) -> str:
    """Append lines under a fixed heading, creating the heading if missing.

    Lines already present in the body are skipped (idempotent merge).
    """
    fresh = [
        line.strip()
        for line in new_lines
        if line and line.strip() and line.strip() not in {
            existing.strip() for existing in body.splitlines()
        }
    ]
    if not fresh:
        return body
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == heading:
            return "\n".join(lines[: index + 1] + [""] + fresh + lines[index + 1 :])
    if body.strip():
        return f"{body.rstrip()}\n\n{heading}\n" + "\n".join(fresh) + "\n"
    return f"{heading}\n" + "\n".join(fresh) + "\n"


def _merge_meta(existing: dict, incoming: dict, source_ids: list[int] | None) -> dict:
    merged = {**existing, **incoming}
    # Aliases accumulate (order-preserving union) instead of being replaced:
    # the memory LLM only reports the name(s) it saw in this window, so
    # replacing them would silently drop every other name (real first names,
    # chat handles, transliterations). That is exactly how the same participant
    # keeps spawning duplicate no-id cards («владимир» splitting off «крабер»,
    # «scrapilla» off «лёха»). Keeping them on one card lets the index resolve
    # every name to the same person.
    seen: set[str] = set()
    merged_aliases: list[str] = []
    for alias in _as_list(existing.get("aliases")) + _as_list(incoming.get("aliases")):
        alias = str(alias).strip()
        if alias and alias not in seen:
            seen.add(alias)
            merged_aliases.append(alias)
    merged["aliases"] = merged_aliases
    if existing.get("created"):
        merged["created"] = existing["created"]
    merged["updated"] = today()
    if source_ids:
        seen = {
            int(x)
            for x in _as_list(merged.get("source_message_ids"))
            if str(x).isdigit()
        }
        seen.update(int(x) for x in source_ids if str(x).isdigit())
        merged["source_message_ids"] = sorted(seen)
    return merged


class KnowledgeVaultWriter:
    def __init__(
        self,
        vault: KnowledgeVault,
        index: KnowledgeIndex | None = None,
        vector_indexer: KnowledgeVectorIndexer | None = None,
    ) -> None:
        self._vault = vault
        self._index = index or KnowledgeIndex(vault)
        self._vector_indexer = vector_indexer

    async def apply(
        self,
        plan: MemoryPlan,
        *,
        source_message_ids: list[int] | None = None,
        mutation_source: str = "post_reply_extract",
    ) -> int:
        """Apply plan updates. Returns the number of files written."""
        if not plan.updates or not self._vault.is_configured:
            return 0
        diffs: list[dict] = []
        self._mutation_source = mutation_source
        self._diffs = diffs
        changed_folders: set[str] = set()
        written_paths: list[str] = []
        for update in plan.updates:
            if not isinstance(update, dict):
                continue
            try:
                folder, paths = await self._apply_update(
                    update,
                    source_message_ids=source_message_ids,
                )
            except Exception:
                logger.exception("knowledge_update_failed update=%r", update)
                continue
            if folder:
                changed_folders.add(folder)
                written_paths.extend(paths)
        for folder in changed_folders:
            await self._index.rebuild_folder(folder)
            written_paths.append(f"{folder}/_index.yaml")
        if self._vector_indexer is not None:
            for path in written_paths:
                try:
                    await self._vector_indexer.index_note(path)
                except Exception:
                    logger.exception(
                        "knowledge_vector_reindex_failed path=%s",
                        path,
                    )
        from vanessa.infrastructure.observability.tracing import get_tracer

        tracer = get_tracer()
        async with tracer.span(
            name="finalize:extract_knowledge",
            metadata={"mutation_source": mutation_source},
            input={"updates": list(plan.updates)},
            output={"written": written_paths, "diff": diffs},
        ):
            pass
        logger.info(
            "knowledge_apply updates=%s written=%s folders=%s",
            len(plan.updates),
            len(written_paths),
            sorted(changed_folders),
        )
        return len(written_paths)

    async def _apply_update(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str | None, list[str]]:
        update_type = str(update.get("type") or "").strip()
        if update_type == "quote":
            return await self._apply_quote(update, source_message_ids)
        if update_type in ("person_mood", "person_fact"):
            return await self._apply_person(update, source_message_ids)
        if update_type == "glossary":
            return await self._apply_glossary(update, source_message_ids)
        if update_type == "event":
            return await self._apply_event(update, source_message_ids)
        if update_type == "recommendation":
            return await self._apply_recommendation(update, source_message_ids)
        if update_type == "weekly_summary":
            return await self._apply_weekly_summary(update, source_message_ids)
        return None, []

    async def _apply_quote(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str, list[str]]:
        person = str(update.get("person") or "").strip()
        quote = str(update.get("quote") or "").strip()
        if not person or not quote:
            return PEOPLE, []
        telegram_id = update.get("telegram_id")
        people_index = await self._index.load_folder(PEOPLE)
        person_id = canonicalize_person(person, telegram_id, people_index)
        if not person_id:
            return PEOPLE, []
        rel = f"{PEOPLE}/{person_id}.md"
        existing = await self._vault.read_note(rel)
        meta = {
            "type": TYPE_PERSON,
            "id": person_id,
            "aliases": _as_list(update.get("aliases")) or [person],
            "created": today(),
            "updated": today(),
        }
        _attach_telegram_id(meta, telegram_id, person_id)
        body = existing.body if existing else self._person_template()
        context = str(update.get("context") or "").strip()
        line = f"> {quote}" + (f" — {context}" if context else "")
        body = _append_to_section(body, "## Цитатник", [line])
        rel = await self._write(rel, meta, body, existing, source_message_ids, keep_sources=False)
        return PEOPLE, [rel]

    async def _apply_person(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str, list[str]]:
        person = str(update.get("person") or "").strip()
        if not person:
            return PEOPLE, []
        telegram_id = update.get("telegram_id")
        people_index = await self._index.load_folder(PEOPLE)
        person_id = canonicalize_person(person, telegram_id, people_index)
        if not person_id:
            return PEOPLE, []
        rel = f"{PEOPLE}/{person_id}.md"
        existing = await self._vault.read_note(rel)
        meta: dict = {
            "type": TYPE_PERSON,
            "id": person_id,
            "aliases": _as_list(update.get("aliases")) or [person],
            "created": today(),
            "updated": today(),
        }
        _attach_telegram_id(meta, telegram_id, person_id)
        body = existing.body if existing else self._person_template()
        update_type = str(update.get("type") or "")
        if update_type == "person_mood":
            mood = str(update.get("mood") or "").strip()
            if mood:
                # The current mood lives in the frontmatter `mood` field — the
                # single source of truth. Never append dated «настроение — …»
                # lines to the body: they pile up into meaningless noise
                # (dozens of near-duplicate single-adjective entries).
                meta["mood"] = mood
        else:
            section = self._person_section(update.get("section"))
            text = str(update.get("text") or "").strip()
            if text:
                body = _append_to_section(body, section, [f"- {today()}: {text}"])
        rel = await self._write(rel, meta, body, existing, source_message_ids, keep_sources=False)
        return PEOPLE, [rel]

    async def _apply_glossary(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str, list[str]]:
        term = str(update.get("term") or "").strip()
        if not term:
            return LORE_GLOSSARY, []
        note_id = slugify(str(update.get("id") or term))
        rel = f"{LORE_GLOSSARY}/{note_id}.md"
        existing = await self._vault.read_note(rel)
        meta = {
            "type": TYPE_GLOSSARY,
            "id": note_id,
            "aliases": _as_list(update.get("aliases")) or [term],
            "created": today(),
            "updated": today(),
        }
        body = existing.body if existing else ""
        definition = str(update.get("definition") or "").strip()
        if definition:
            body = _append_to_section(body, "## Значение", [definition])
        quote = str(update.get("first_quote") or "").strip()
        if quote:
            body = _append_to_section(body, "## Пример", [f"> {quote}"])
        rel = await self._write(rel, meta, body, existing, source_message_ids)
        return LORE_GLOSSARY, [rel]

    async def _apply_event(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str, list[str]]:
        title = str(update.get("title") or "").strip()
        if not title:
            return LORE_EVENTS, []
        date_str = str(update.get("date") or today())
        note_id = slugify(str(update.get("id") or title))
        rel = f"{LORE_EVENTS}/{date_str}-{note_id}.md"
        existing = await self._vault.read_note(rel)
        meta = {
            "type": TYPE_EVENT,
            "id": note_id,
            "title": title,
            "date": date_str,
            "participants": _as_list(update.get("participants")),
            "created": today(),
            "updated": today(),
        }
        body = existing.body if existing else ""
        summary = str(update.get("summary") or update.get("text") or "").strip()
        if summary:
            body = _append_to_section(body, "## Суть", [summary])
        outcome = str(update.get("outcome") or "").strip()
        if outcome:
            body = _append_to_section(body, "## Чем закончилось", [outcome])
        rel = await self._write(rel, meta, body, existing, source_message_ids)
        return LORE_EVENTS, [rel]

    async def _apply_recommendation(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str, list[str]]:
        kind = str(update.get("kind") or "").strip()
        folder = culture_kind_folder(kind)
        if folder is None:
            return CULTURE, []
        title = str(update.get("title") or "").strip()
        if not title:
            return CULTURE, []
        note_id = slugify(str(update.get("id") or title))
        rel = f"{folder}/{note_id}.md"
        existing = await self._vault.read_note(rel)
        status = str(update.get("status") or "").strip() or (
            existing.meta.get("status") if existing else "proposed"
        )
        meta: dict = {
            "type": TYPE_RECOMMENDATION,
            "id": note_id,
            "kind": kind,
            "title": title,
            "status": status,
            "recommended_by": str(update.get("recommended_by") or ""),
            "created": today(),
            "updated": today(),
        }
        rating = update.get("rating")
        if rating is not None:
            meta["rating"] = rating
        body = existing.body if existing else ""
        description = str(update.get("description") or update.get("summary") or "").strip()
        if description:
            body = _append_to_section(body, "## Описание", [description])
        rel = await self._write(rel, meta, body, existing, source_message_ids)
        return CULTURE, [rel]

    async def _apply_weekly_summary(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str, list[str]]:
        summary = str(update.get("summary") or update.get("text") or "").strip()
        if not summary:
            return LOGS, []
        year_week = self._year_week()
        rel = f"{LOGS_WEEKLY}/{year_week}.md"
        existing = await self._vault.read_note(rel)
        meta = {
            "type": TYPE_LOG,
            "period": "weekly",
            "created": today(),
            "updated": today(),
        }
        body = existing.body if existing else ""
        body = _append_to_section(body, "## Темы", [f"- {summary}"])
        rel = await self._write(rel, meta, body, existing, source_message_ids)
        return LOGS, [rel]

    async def _write(
        self,
        relative_path: str,
        meta: dict,
        body: str,
        existing: VaultNote | None,
        source_message_ids: list[int] | None,
        *,
        keep_sources: bool = True,
    ) -> str:
        merged_meta = _merge_meta(
            existing.meta if existing else {},
            meta,
            source_message_ids if keep_sources else None,
        )
        if not keep_sources:
            merged_meta.pop("source_message_ids", None)
        old_body = existing.body if existing else ""
        rel = await self._vault.write_note(
            relative_path,
            merged_meta,
            body,
            mutation_source=getattr(self, "_mutation_source", "direct"),
        )
        diffs = getattr(self, "_diffs", None)
        if diffs is not None and old_body != body:
            diffs.append(
                {
                    "path": rel,
                    "before": old_body,
                    "after": body,
                }
            )
        return rel

    @staticmethod
    def _person_template() -> str:
        return (
            "## Контекст жизни\n\n"
            "## Цитатник\n\n"
            "## Хроника"
        )

    @staticmethod
    def _person_section(key: object) -> str:
        # «Триггеры и темы» is redundant with «Контекст жизни» — both are dated
        # facts — so everything routes to the single context section.
        mapping = {
            "triggers": "## Контекст жизни",
            "context": "## Контекст жизни",
            "mood": "## Настрой и метрики",
            "quotes": "## Цитатник",
        }
        key = (key or "").strip().lower()
        if key.startswith("##"):
            return key
        return mapping.get(key, "## Контекст жизни")

    @staticmethod
    def _year_week() -> str:
        iso = datetime.now().astimezone().date().isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
