"""Apply dated-section compaction to one person card."""

from __future__ import annotations

import logging
from datetime import date

from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.memory.compaction_archive import append_archive
from vanessa.knowledge.memory.compaction_body import (
    compact_heading_lines,
    join_sections,
)
from vanessa.knowledge.store.vault import KnowledgeVault

logger = logging.getLogger("vanessa.knowledge.memory.compaction")


async def compact_heading(
    vault: KnowledgeVault,
    person_id: str,
    heading: str,
    lines: list[str],
    today_: date,
    limit: int,
    quote_limit: int,
) -> tuple[list[str], int, bool] | None:
    kept, overflow = compact_heading_lines(
        heading, lines, today_, limit, quote_limit
    )
    if kept is None:
        return None
    if overflow:
        await append_archive(vault, person_id, heading, overflow)
    return kept, len(overflow), kept != lines


async def compact_sections(
    vault: KnowledgeVault,
    person_id: str,
    sections: list[tuple[str, list[str]]],
    today_: date,
    limit: int,
    quote_limit: int,
) -> tuple[int, int, bool]:
    kept_total = 0
    archived_total = 0
    changed = False
    for index, (heading, lines) in enumerate(sections):
        result = await compact_heading(
            vault, person_id, heading, lines, today_, limit, quote_limit
        )
        if result is None:
            continue
        kept, archived, section_changed = result
        kept_total += len(kept)
        archived_total += archived
        if section_changed:
            sections[index] = (heading, kept)
            changed = True
    return kept_total, archived_total, changed


async def write_compacted_card(
    vault: KnowledgeVault,
    person_id: str,
    note,
    sections: list[tuple[str, list[str]]],
    kept_total: int,
    archived_total: int,
) -> tuple[int, int, bool]:
    body = join_sections(sections)
    # Only rewrite when the body actually changes: `kept != lines` can be a
    # false positive (blank-line round-tripping), and a no-op write would still
    # trigger a uvicorn reload on every sweep.
    if body == (note.body or ""):
        return kept_total, archived_total, False
    rel = f"{PEOPLE}/{person_id}.md"
    await vault.write_note(rel, dict(note.meta), body)
    logger.info(
        "knowledge_compacted person=%s kept=%s archived=%s",
        person_id,
        kept_total,
        archived_total,
    )
    return kept_total, archived_total, True
