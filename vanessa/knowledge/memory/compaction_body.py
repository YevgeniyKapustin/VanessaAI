"""Dated-section and quote compaction for person-card bodies."""

from __future__ import annotations

import re
from datetime import date

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


def split_sections(body: str) -> list[tuple[str, list[str]]]:
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


def join_sections(sections: list[tuple[str, list[str]]]) -> str:
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


def _split_dated_lines(lines: list[str]) -> tuple[list[tuple[date, str]], list[str]]:
    dated: list[tuple[date, str]] = []
    undated: list[str] = []
    for line in lines:
        if not line.strip():
            continue  # drop blank separators
        line_date = parse_line_date(line)
        if line_date is not None:
            dated.append((line_date, line))
            continue
        undated.append(line)
    return dated, undated


def _take_bucket(
    bucket: list[tuple[date, str]],
    limit: int,
    kept: list[tuple[date, str]],
    overflow: list[str],
) -> None:
    # bucket is ascending; the newest are the LAST entries.
    if len(bucket) > limit:
        kept.extend(bucket[-limit:])
        overflow.extend(line for _, line in bucket[:-limit])
        return
    kept.extend(bucket)


def _keep_bucket_entries(
    dated: list[tuple[date, str]],
    today_: date,
    limit: int,
) -> tuple[list[tuple[date, str]], list[str]]:
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
        _take_bucket(by_bucket.get(key, []), limit, kept, overflow)
    kept.sort(key=lambda item: item[0])
    return kept, overflow


def compact_section(
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
    dated, undated = _split_dated_lines(lines)
    if not dated:
        return list(lines), []
    kept, overflow = _keep_bucket_entries(dated, today_, limit)
    return undated + [line for _, line in kept], overflow


def _unique_quote_lines(lines: list[str]) -> list[str]:
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
    return quotes


def compact_quotes(
    lines: list[str],
    *,
    limit: int = QUOTE_LIMIT,
) -> tuple[list[str], list[str]]:
    """Keep the newest ``limit`` non-duplicate quotes; archive the rest.

    «Цитатник» lines are undated ``> …`` entries appended in chronological
    order, so the newest are the LAST ones. Exact duplicates are dropped.
    """
    quotes = _unique_quote_lines(lines)
    if len(quotes) <= limit:
        return list(lines), []
    return quotes[-limit:], quotes[:-limit]


def compact_heading_lines(
    heading: str,
    lines: list[str],
    today_: date,
    limit: int,
    quote_limit: int,
) -> tuple[list[str], list[str]] | tuple[None, None]:
    if heading == "## Цитатник":
        return compact_quotes(lines, limit=quote_limit)
    if heading in COMPACT_SECTIONS:
        return compact_section(lines, today_, limit=limit)
    return None, None
