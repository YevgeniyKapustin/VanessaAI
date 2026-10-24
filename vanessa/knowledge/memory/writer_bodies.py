"""Body builders for lore and culture cards (one section per planner field)."""

from __future__ import annotations

from vanessa.knowledge.memory.writer_fields import note_body, stripped_text
from vanessa.knowledge.memory.writer_merge import append_to_section


def append_sections(body: str, sections: tuple[tuple[str, str], ...]) -> str:
    """Append each non-empty ``(heading, line)`` to its section."""
    for heading, line in sections:
        if line:
            body = append_to_section(body, heading, [line])
    return body


def quoted(text: str) -> str:
    return f"> {text}" if text else ""


def glossary_body(update: dict, existing: object) -> str:
    return append_sections(
        note_body(existing),
        (
            ("## Значение", stripped_text(update.get("definition"))),
            ("## Пример", quoted(stripped_text(update.get("first_quote")))),
        ),
    )


def event_body(update: dict, existing: object) -> str:
    return append_sections(
        note_body(existing),
        (
            ("## Суть", stripped_text(update.get("summary"), update.get("text"))),
            ("## Чем закончилось", stripped_text(update.get("outcome"))),
        ),
    )


def recommendation_body(update: dict, existing: object) -> str:
    description = stripped_text(update.get("description"), update.get("summary"))
    return append_sections(note_body(existing), (("## Описание", description),))
