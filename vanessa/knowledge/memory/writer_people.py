"""Person-card update handlers for KnowledgeVaultWriter."""

from __future__ import annotations

from vanessa.knowledge.format import PEOPLE, TYPE_PERSON, today
from vanessa.knowledge.memory.writer_fields import list_or_default, stripped_text
from vanessa.knowledge.memory.writer_merge import (
    append_to_section,
    attach_telegram_id,
)
from vanessa.knowledge.people.people import canonicalize_person


class WriterPeopleUpdates:
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
            "aliases": list_or_default(update.get("aliases"), [person]),
            "created": today(),
            "updated": today(),
        }
        attach_telegram_id(meta, telegram_id, person_id)
        body = existing.body if existing else self._person_template()
        context = str(update.get("context") or "").strip()
        line = f"> {quote}" + (f" — {context}" if context else "")
        body = append_to_section(body, "## Цитатник", [line])
        rel = await self._write(rel, meta, body, existing, source_message_ids, keep_sources=False)
        return PEOPLE, [rel]

    def _apply_mood_or_fact(self, update: dict, meta: dict, body: str) -> str:
        if str(update.get("type") or "") == "person_mood":
            mood = stripped_text(update.get("mood"))
            if mood:
                # The current mood lives in the frontmatter `mood` field — the
                # single source of truth. Never append dated «настроение — …»
                # lines to the body: they pile up into meaningless noise
                # (dozens of near-duplicate single-adjective entries).
                meta["mood"] = mood
            return body
        text = stripped_text(update.get("text"))
        if not text:
            return body
        section = self._person_section(update.get("section"))
        return append_to_section(body, section, [f"- {today()}: {text}"])

    async def _apply_person(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str, list[str]]:
        person = stripped_text(update.get("person"))
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
            "aliases": list_or_default(update.get("aliases"), [person]),
            "created": today(),
            "updated": today(),
        }
        attach_telegram_id(meta, telegram_id, person_id)
        body = existing.body if existing else self._person_template()
        body = self._apply_mood_or_fact(update, meta, body)
        rel = await self._write(rel, meta, body, existing, source_message_ids, keep_sources=False)
        return PEOPLE, [rel]
