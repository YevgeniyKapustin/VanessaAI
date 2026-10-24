"""Person-card context compaction: bounded, time-sampled memory.

«Контекст жизни» (and any other dated section in ``COMPACT_SECTIONS``) collects
every dated fact the memory planner writes and grows without bound. Compaction
keeps a bounded, time-sampled view — the newest ``limit`` entries per age bucket
(today, this week, this month, 3 months, 6 months, this year, older) — sorted
by date. «Цитатник» is undated, so it is capped to the newest ``QUOTE_LIMIT``
non-duplicate quotes instead. In both cases the overflow moves into an
append-only archive under ``knowledge/_archive/``. The archive deliberately
lives OUTSIDE the semantic folders (People/Lore/Culture/Logs), so no index and
no vector is ever built for it: it is a pure, unused backup of the trimmed
records.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from vanessa.core.chat_zone import chat_now
from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.memory.compaction_apply import (
    compact_sections,
    write_compacted_card,
)
from vanessa.knowledge.memory.compaction_archive import ARCHIVE_PEOPLE
from vanessa.knowledge.memory.compaction_body import (
    BUCKETS,
    COMPACT_SECTIONS,
    LIMIT,
    QUOTE_LIMIT,
    age_days,
    bucket_key,
    parse_line_date,
    split_sections,
)
from vanessa.knowledge.store.vault import KnowledgeVault

logger = logging.getLogger(__name__)

__all__ = [
    "ARCHIVE_PEOPLE",
    "BUCKETS",
    "COMPACT_SECTIONS",
    "LIMIT",
    "QUOTE_LIMIT",
    "age_days",
    "bucket_key",
    "compact_all_person_cards",
    "compact_person_card",
    "parse_line_date",
]


async def compact_person_card(
    vault: KnowledgeVault,
    person_id: str,
    *,
    today_: date | None = None,
    limit: int = LIMIT,
    quote_limit: int = QUOTE_LIMIT,
) -> tuple[int, int, bool]:
    """Compact one person card. Returns ``(kept, archived, changed)``."""
    today_ = today_ or chat_now().date()
    rel = f"{PEOPLE}/{person_id}.md"
    note = await vault.read_note(rel)
    if note is None:
        return 0, 0, False
    sections = split_sections(note.body)
    kept_total, archived_total, changed = await compact_sections(
        vault, person_id, sections, today_, limit, quote_limit
    )
    if not changed:
        return kept_total, archived_total, False
    return await write_compacted_card(
        vault, person_id, note, sections, kept_total, archived_total
    )


async def _compact_note_safe(
    vault: KnowledgeVault,
    note,
    *,
    today_: date | None,
    limit: int,
    quote_limit: int,
) -> tuple[int, bool]:
    person_id = Path(note.relative_path).stem
    try:
        _kept, added, changed = await compact_person_card(
            vault, person_id, today_=today_, limit=limit, quote_limit=quote_limit
        )
    except Exception:
        logger.exception("knowledge_compaction_failed person=%s", person_id)
        return 0, False
    return added, changed


def _log_compaction_done(files_changed: int, archived: int) -> None:
    if not files_changed and not archived:
        return
    logger.info(
        "knowledge_compaction_done files_changed=%s archived_lines=%s",
        files_changed,
        archived,
    )


async def compact_all_person_cards(
    vault: KnowledgeVault,
    *,
    today_: date | None = None,
    limit: int = LIMIT,
    quote_limit: int = QUOTE_LIMIT,
) -> tuple[int, int]:
    """Compact every person card. Returns ``(files_changed, archived_lines)``."""
    if not vault.is_configured:
        return 0, 0
    notes = await vault.list_notes(PEOPLE)
    files_changed = 0
    archived = 0
    for note in notes:
        added, changed = await _compact_note_safe(
            vault, note, today_=today_, limit=limit, quote_limit=quote_limit
        )
        if changed:
            files_changed += 1
        archived += added
    _log_compaction_done(files_changed, archived)
    return files_changed, archived
