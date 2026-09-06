"""Glossary, event, culture, and weekly-log update handlers."""

from __future__ import annotations

from vanessa.knowledge.format import (
    CULTURE,
    LOGS,
    LOGS_WEEKLY,
    LORE_EVENTS,
    LORE_GLOSSARY,
    TYPE_EVENT,
    TYPE_GLOSSARY,
    TYPE_LOG,
    slugify,
    today,
)
from vanessa.knowledge.memory.writer_fields import (
    first_str,
    list_or_default,
    note_body,
    stripped_text,
)
from vanessa.knowledge.memory.writer_merge import append_to_section, as_list
from vanessa.knowledge.memory.writer_recommendation import (
    recommendation_meta,
    recommendation_status,
    recommendation_target,
)


class WriterNoteUpdates:
    async def _apply_glossary(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str, list[str]]:
        term = stripped_text(update.get("term"))
        if not term:
            return LORE_GLOSSARY, []
        note_id = slugify(first_str(update.get("id"), term))
        rel = f"{LORE_GLOSSARY}/{note_id}.md"
        existing = await self._vault.read_note(rel)
        meta = {
            "type": TYPE_GLOSSARY,
            "id": note_id,
            "aliases": list_or_default(update.get("aliases"), [term]),
            "created": today(),
            "updated": today(),
        }
        body = note_body(existing)
        definition = stripped_text(update.get("definition"))
        if definition:
            body = append_to_section(body, "## Значение", [definition])
        quote = stripped_text(update.get("first_quote"))
        if quote:
            body = append_to_section(body, "## Пример", [f"> {quote}"])
        rel = await self._write(rel, meta, body, existing, source_message_ids)
        return LORE_GLOSSARY, [rel]

    async def _apply_event(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str, list[str]]:
        title = stripped_text(update.get("title"))
        if not title:
            return LORE_EVENTS, []
        date_str = first_str(update.get("date")) or today()
        note_id = slugify(first_str(update.get("id"), title))
        rel = f"{LORE_EVENTS}/{date_str}-{note_id}.md"
        existing = await self._vault.read_note(rel)
        meta = {
            "type": TYPE_EVENT,
            "id": note_id,
            "title": title,
            "date": date_str,
            "participants": as_list(update.get("participants")),
            "created": today(),
            "updated": today(),
        }
        body = note_body(existing)
        summary = stripped_text(update.get("summary"), update.get("text"))
        if summary:
            body = append_to_section(body, "## Суть", [summary])
        outcome = stripped_text(update.get("outcome"))
        if outcome:
            body = append_to_section(body, "## Чем закончилось", [outcome])
        rel = await self._write(rel, meta, body, existing, source_message_ids)
        return LORE_EVENTS, [rel]

    async def _apply_recommendation(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str, list[str]]:
        target = recommendation_target(update)
        if target is None:
            return CULTURE, []
        folder, kind, title, note_id = target
        rel = f"{folder}/{note_id}.md"
        existing = await self._vault.read_note(rel)
        meta = recommendation_meta(
            update,
            note_id=note_id,
            kind=kind,
            title=title,
            status=recommendation_status(update, existing),
        )
        body = note_body(existing)
        description = stripped_text(update.get("description"), update.get("summary"))
        if description:
            body = append_to_section(body, "## Описание", [description])
        rel = await self._write(rel, meta, body, existing, source_message_ids)
        return CULTURE, [rel]

    async def _apply_weekly_summary(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str, list[str]]:
        summary = stripped_text(update.get("summary"), update.get("text"))
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
        body = note_body(existing)
        body = append_to_section(body, "## Темы", [f"- {summary}"])
        rel = await self._write(rel, meta, body, existing, source_message_ids)
        return LOGS, [rel]
