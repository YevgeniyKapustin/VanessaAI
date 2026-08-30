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
import re
from datetime import date, datetime
from pathlib import Path

from vanessa.knowledge.format import PEOPLE, today
from vanessa.knowledge.vault import KnowledgeVault

logger = logging.getLogger(__name__)

# Top-level archive area. NOT in ALL_FOLDERS, NOT in the vector indexer's
# semantic folders — the bot never reads it for retrieval or embedding.
ARCHIVE_PEOPLE = "_archive/People"

# Body sections that get compacted. «Триггеры и темы» and «Цитатник» keep their
# (small) content untouched.
COMPACT_SECTIONS = ("## Контекст жизни",)

# Age buckets, oldest -> newest, as (key, max_age_days). Each bucket keeps at
# most LIMIT entries. ``older`` is unbounded (> 1 year).
BUCKETS: tuple[tuple[str, int | float], ...] = (
    ("older", float("inf")),  # > 1 year
    ("year", 365),            # 181-365 days
    ("months_6", 180),        # 91-180 days
    ("months_3", 90),         # 31-90 days
    ("month", 30),            # 8-30 days
    ("week", 7),              # 1-7 days
    ("today", 0),             # today
)
LIMIT = 10

# «Цитатник» is undated, so a flat cap (newest N non-duplicate quotes).
QUOTE_LIMIT = 20

_DATED = re.compile(r"^-\s+(\d{4})-(\d{2})-(\d{2}):")


def parse_line_date(line: str) -> date | None:
    """Extract ``YYYY-MM-DD`` from a ``- 2026-08-27: …`` line, else None."""
    match = _DATED.match(line)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def age_days(line_date: date, today_: date) -> int:
    """Whole days since ``line_date`` (clamped to >= 0 for future dates)."""
    return max(0, (today_ - line_date).days)


def bucket_key(age: int) -> str:
    """Return the bucket name for a given age in days.

    Newest bucket first: age 0 must land in ``today``, age 3 in ``week``, etc.,
    not in the unbounded ``older`` bucket.
    """
    for key, max_age in reversed(BUCKETS):
        if age <= max_age:
            return key
    return "older"


def _split_sections(body: str) -> list[tuple[str, list[str]]]:
    """[(heading, lines)] preserving order; heading == "" for the preamble."""
    sections: list[tuple[str, list[str]]] = []
    heading = ""
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("## "):
            sections.append((heading, lines))
            heading = line.strip()
            lines = []
        else:
            lines.append(line)
    sections.append((heading, lines))
    return sections


def _join_sections(sections: list[tuple[str, list[str]]]) -> str:
    parts: list[str] = []
    for heading, lines in sections:
        if not heading:
            parts.extend(lines)
            continue
        # Exactly one blank line separates sections.
        if parts and parts[-1] != "":
            parts.append("")
        parts.append(heading)
        parts.extend(lines)
    return "\n".join(parts)


def _compact_section(
    lines: list[str],
    today_: date,
    *,
    limit: int = LIMIT,
) -> tuple[list[str], list[str]]:
    """Return ``(kept_lines, overflow_lines)`` for a dated body section.

    Keeps the newest ``limit`` entries per age bucket (sorted chronologically)
    and returns the trimmed remainder as overflow. Non-dated lines are kept at
    the top, untouched.
    """
    dated: list[tuple[date, str]] = []
    undated: list[str] = []
    for line in lines:
        if not line.strip():
            continue  # drop blank separators
        line_date = parse_line_date(line)
        if line_date is not None:
            dated.append((line_date, line))
        else:
            undated.append(line)

    if not dated:
        return list(lines), []

    # Stable sort by date (oldest first); equal dates keep insertion order.
    dated.sort(key=lambda item: item[0])

    by_bucket: dict[str, list[tuple[date, str]]] = {}
    for line_date, line in dated:
        by_bucket.setdefault(bucket_key(age_days(line_date, today_)), []).append(
            (line_date, line)
        )

    kept: list[tuple[date, str]] = []
    overflow: list[str] = []
    for key, _max_age in BUCKETS:
        bucket = by_bucket.get(key, [])
        # bucket is ascending; the newest are the LAST entries.
        if len(bucket) > limit:
            kept.extend(bucket[-limit:])
            overflow.extend(line for _, line in bucket[:-limit])
        else:
            kept.extend(bucket)

    kept.sort(key=lambda item: item[0])
    return undated + [line for _, line in kept], overflow


def _compact_quotes(
    lines: list[str],
    *,
    limit: int = QUOTE_LIMIT,
) -> tuple[list[str], list[str]]:
    """Keep the newest ``limit`` non-duplicate quotes; archive the rest.

    «Цитатник» lines are undated ``> …`` entries appended in chronological
    order, so the newest are the LAST ones. Exact duplicates are dropped.
    """
    quotes: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        key = line.strip()
        if key in seen:
            continue
        seen.add(key)
        quotes.append(line)
    if len(quotes) <= limit:
        return list(lines), []
    return quotes[-limit:], quotes[:-limit]


async def _append_archive(
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
    seen = {line.strip() for line in body.splitlines()}
    fresh = [line for line in lines if line.strip() and line.strip() not in seen]
    if not fresh:
        return 0
    sections = _split_sections(body)
    reused = False
    for index, (existing_heading, section_lines) in enumerate(sections):
        if existing_heading == heading:
            sections[index] = (existing_heading, section_lines + fresh)
            reused = True
            break
    if not reused:
        sections.append((heading, fresh))
    meta = {"type": "archive", "id": person_id, "updated": today()}
    await vault.write_note(rel, meta, _join_sections(sections))
    return len(fresh)


async def compact_person_card(
    vault: KnowledgeVault,
    person_id: str,
    *,
    today_: date | None = None,
    limit: int = LIMIT,
    quote_limit: int = QUOTE_LIMIT,
) -> tuple[int, int, bool]:
    """Compact one person card. Returns ``(kept, archived, changed)``."""
    today_ = today_ or datetime.now().astimezone().date()
    rel = f"{PEOPLE}/{person_id}.md"
    note = await vault.read_note(rel)
    if note is None:
        return 0, 0, False

    sections = _split_sections(note.body)
    kept_total = 0
    archived_total = 0
    changed = False
    for index, (heading, lines) in enumerate(sections):
        if heading == "## Цитатник":
            kept, overflow = _compact_quotes(lines, limit=quote_limit)
        elif heading in COMPACT_SECTIONS:
            kept, overflow = _compact_section(lines, today_, limit=limit)
        else:
            continue
        kept_total += len(kept)
        archived_total += len(overflow)
        if overflow:
            await _append_archive(vault, person_id, heading, overflow)
        if kept != lines:
            sections[index] = (heading, kept)
            changed = True

    if not changed:
        return kept_total, archived_total, False
    body = _join_sections(sections)
    # Only rewrite when the body actually changes: `kept != lines` can be a
    # false positive (blank-line round-tripping), and a no-op write would still
    # trigger a uvicorn reload on every sweep.
    if body == (note.body or ""):
        return kept_total, archived_total, False
    await vault.write_note(rel, dict(note.meta), body)
    logger.info("knowledge_compacted person=%s kept=%s archived=%s", person_id, kept_total, archived_total)
    return kept_total, archived_total, True


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
        person_id = Path(note.relative_path).stem
        try:
            _kept, added, changed = await compact_person_card(
                vault, person_id, today_=today_, limit=limit, quote_limit=quote_limit
            )
        except Exception:
            logger.exception("knowledge_compaction_failed person=%s", person_id)
            continue
        if changed:
            files_changed += 1
        archived += added
    if files_changed or archived:
        logger.info("knowledge_compaction_done files_changed=%s archived_lines=%s", files_changed, archived)
    return files_changed, archived
