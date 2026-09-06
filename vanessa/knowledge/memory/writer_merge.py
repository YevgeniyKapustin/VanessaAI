"""Idempotent merge helpers for vault note updates."""

from __future__ import annotations

from datetime import datetime

from vanessa.knowledge.format import today
from vanessa.knowledge.people.people import telegram_id_for_slug


def attach_telegram_id(meta: dict, telegram_id: object, person_id: str) -> None:
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


def as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _usable_section_line(line: str, existing: set[str]) -> str | None:
    if not line:
        return None
    text = line.strip()
    if not text:
        return None
    if text in existing:
        return None
    return text


def _fresh_section_lines(body: str, new_lines: list[str]) -> list[str]:
    existing = {line.strip() for line in body.splitlines()}
    fresh: list[str] = []
    for line in new_lines:
        text = _usable_section_line(line, existing)
        if text is not None:
            fresh.append(text)
    return fresh


def _insert_under_heading(body: str, heading: str, fresh: list[str]) -> str:
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == heading:
            return "\n".join([*lines[: index + 1], "", *fresh, *lines[index + 1 :]])
    if body.strip():
        return f"{body.rstrip()}\n\n{heading}\n" + "\n".join(fresh) + "\n"
    return f"{heading}\n" + "\n".join(fresh) + "\n"


def append_to_section(body: str, heading: str, new_lines: list[str]) -> str:
    """Append lines under a fixed heading, creating the heading if missing.

    Lines already present in the body are skipped (idempotent merge).
    """
    fresh = _fresh_section_lines(body, new_lines)
    if not fresh:
        return body
    return _insert_under_heading(body, heading, fresh)


def _merged_aliases(existing: dict, incoming: dict) -> list[str]:
    seen: set[str] = set()
    merged_aliases: list[str] = []
    for raw_alias in as_list(existing.get("aliases")) + as_list(
        incoming.get("aliases")
    ):
        alias = str(raw_alias).strip()
        if alias and alias not in seen:
            seen.add(alias)
            merged_aliases.append(alias)
    return merged_aliases


def _merged_source_ids(merged: dict, source_ids: list[int] | None) -> None:
    if not source_ids:
        return
    seen = {
        int(x)
        for x in as_list(merged.get("source_message_ids"))
        if str(x).isdigit()
    }
    seen.update(int(x) for x in source_ids if str(x).isdigit())
    merged["source_message_ids"] = sorted(seen)


def merge_meta(existing: dict, incoming: dict, source_ids: list[int] | None) -> dict:
    merged = {**existing, **incoming}
    # Aliases accumulate (order-preserving union) instead of being replaced:
    # the memory LLM only reports the name(s) it saw in this window, so
    # replacing them would silently drop every other name (real first names,
    # chat handles, transliterations). That is exactly how the same participant
    # keeps spawning duplicate no-id cards («владимир» splitting off «крабер»,
    # «scrapilla» off «лёха»). Keeping them on one card lets the index resolve
    # every name to the same person.
    merged["aliases"] = _merged_aliases(existing, incoming)
    if existing.get("created"):
        merged["created"] = existing["created"]
    merged["updated"] = today()
    _merged_source_ids(merged, source_ids)
    return merged


class WriterTemplates:
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
