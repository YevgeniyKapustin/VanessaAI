"""Append overflow person-card lines to the unused archive area."""

from __future__ import annotations

from vanessa.knowledge.format import today
from vanessa.knowledge.memory.compaction_body import join_sections, split_sections
from vanessa.knowledge.store.vault import KnowledgeVault

ARCHIVE_PEOPLE = "_archive/People"


def _fresh_archive_lines(body: str, lines: list[str]) -> list[str]:
    seen = {line.strip() for line in body.splitlines()}
    fresh: list[str] = []
    for line in lines:
        key = line.strip()
        if not key:
            continue
        if key in seen:
            continue
        fresh.append(line)
    return fresh


def _merge_archive_section(
    sections: list[tuple[str, list[str]]],
    heading: str,
    fresh: list[str],
) -> None:
    for index, (existing_heading, section_lines) in enumerate(sections):
        if existing_heading == heading:
            sections[index] = (existing_heading, section_lines + fresh)
            return
    sections.append((heading, fresh))


async def append_archive(
    vault: KnowledgeVault,
    person_id: str,
    heading: str,
    lines: list[str],
) -> int:
    """Append overflow lines to ``_archive/People/{id}.md`` (deduped)."""
    if not lines:
        return 0
    rel = f"{ARCHIVE_PEOPLE}/{person_id}.md"
    existing = await vault.read_note(rel)
    body = existing.body if existing is not None else ""
    fresh = _fresh_archive_lines(body, lines)
    if not fresh:
        return 0
    sections = split_sections(body)
    _merge_archive_section(sections, heading, fresh)
    meta = {"type": "archive", "id": person_id, "updated": today()}
    await vault.write_note(rel, meta, join_sections(sections))
    return len(fresh)
