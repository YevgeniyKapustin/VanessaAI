"""Person-card update handlers for KnowledgeVaultWriter."""

from __future__ import annotations

from vanessa.knowledge.format import PEOPLE, TYPE_PERSON, today
from vanessa.knowledge.memory.writer_fields import list_or_default, stripped_text
from vanessa.knowledge.memory.writer_merge import (
    append_to_section,
    attach_telegram_id,
)
from vanessa.knowledge.people.vrchat_speaker import PersonCard, resolve_person_card


def _update_channel(update: dict) -> str:
    return str(update.get("channel") or "")


def _card_for_update(person: str, update: dict, people_index: dict) -> PersonCard:
    return resolve_person_card(
        person,
        update.get("telegram_id"),
        people_index,
        channel=_update_channel(update) or None,
    )


def _bind_card_telegram(meta: dict, card: PersonCard, update: dict) -> None:
    if _update_channel(update) == "vrchat":
        if card.telegram_id is not None:
            attach_telegram_id(meta, card.telegram_id, card.person_id)
        return
    attach_telegram_id(meta, update.get("telegram_id"), card.person_id)


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
        people_index = await self._index.load_folder(PEOPLE)
        card = _card_for_update(person, update, people_index)
        if not card.person_id:
            return PEOPLE, []
        rel = f"{PEOPLE}/{card.person_id}.md"
        existing = await self._vault.read_note(rel)
        meta = {
            "type": TYPE_PERSON,
            "id": card.person_id,
            "aliases": list_or_default(update.get("aliases"), [person]),
            "created": today(),
            "updated": today(),
        }
        _bind_card_telegram(meta, card, update)
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
        people_index = await self._index.load_folder(PEOPLE)
        card = _card_for_update(person, update, people_index)
        if not card.person_id:
            return PEOPLE, []
        rel = f"{PEOPLE}/{card.person_id}.md"
        existing = await self._vault.read_note(rel)
        meta: dict = {
            "type": TYPE_PERSON,
            "id": card.person_id,
            "aliases": list_or_default(update.get("aliases"), [person]),
            "created": today(),
            "updated": today(),
        }
        _bind_card_telegram(meta, card, update)
        body = existing.body if existing else self._person_template()
        body = self._apply_mood_or_fact(update, meta, body)
        rel = await self._write(rel, meta, body, existing, source_message_ids, keep_sources=False)
        return PEOPLE, [rel]
