"""Machine-only knowledge-vault format: folder taxonomy, slugs, frontmatter.

The vault is written and read exclusively by the bot — no human browses it — so
the format is a deterministic contract for the LLM: stable per-entity files,
typed YAML frontmatter, fixed section headings, and per-folder ``_index.yaml``
machine manifests. There is intentionally no human MOC / wikilink layer.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath

import yaml

# Folder taxonomy.
PEOPLE = "People"
LORE = "Lore"
LORE_GLOSSARY = "Lore/glossary"
LORE_EVENTS = "Lore/events"
CULTURE = "Culture"
CULTURE_KINDS: tuple[str, ...] = ("movies", "games", "music")
LOGS = "Logs"
LOGS_DAILY = "Logs/daily"
LOGS_WEEKLY = "Logs/weekly"
INBOX = "inbox"

# Every storage folder (each keeps its own _index.yaml). Metrics live inside
# the person cards (frontmatter `metrics` block) — the single source of truth —
# so there is no separate Metrics/ folder.
ALL_FOLDERS: tuple[str, ...] = (
    PEOPLE,
    LORE_GLOSSARY,
    LORE_EVENTS,
    CULTURE,
    LOGS_DAILY,
    LOGS_WEEKLY,
    INBOX,
)

INDEX_FILENAME = "_index.yaml"

# Note types (frontmatter `type`).
TYPE_INDEX = "index"
TYPE_PERSON = "person"
TYPE_GLOSSARY = "glossary"
TYPE_EVENT = "event"
TYPE_RECOMMENDATION = "recommendation"
TYPE_LOG = "log"
TYPE_NOTE = "note"

_FRONTMATTER_DELIM = "---"
_UNSAFE_CHARS = re.compile(r"[^\w\-]+", re.UNICODE)
_DASHES = re.compile(r"-+")


def slugify(value: str) -> str:
    """Stable filesystem-safe slug; keeps unicode letters/digits (cyrillic ok)."""
    cleaned = _UNSAFE_CHARS.sub("-", value.strip().lower())
    cleaned = _DASHES.sub("-", cleaned).strip("-")
    return cleaned or "untitled"


def today() -> str:
    """Today's date as ``YYYY-MM-DD`` (local)."""
    return datetime.now().astimezone().date().isoformat()


def culture_kind_folder(kind: str) -> str | None:
    """Return ``Culture/<kind>`` for a supported kind, else None."""
    return f"{CULTURE}/{kind}" if kind in CULTURE_KINDS else None


def render_frontmatter(meta: dict) -> str:
    """Render a meta dict as a YAML frontmatter block (empty when meta empty)."""
    if not meta:
        return ""
    body = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"{_FRONTMATTER_DELIM}\n{body}\n{_FRONTMATTER_DELIM}"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown document into (meta, body). Falls back to ({}, text)."""
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith(_FRONTMATTER_DELIM):
        return {}, stripped
    lines = stripped.splitlines()
    if len(lines) < 3:
        return {}, stripped
    fm_lines: list[str] = []
    body_start = 0
    for index in range(1, len(lines)):
        if lines[index].strip() == _FRONTMATTER_DELIM:
            body_start = index + 1
            break
        fm_lines.append(lines[index])
    else:
        return {}, stripped
    body = "\n".join(lines[body_start:]).strip("\n")
    try:
        meta = yaml.safe_load("\n".join(fm_lines)) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, body


def render_note(meta: dict, body: str) -> str:
    """Render (meta, body) into a full note document string."""
    parts = [part for part in (render_frontmatter(meta), body.strip()) if part]
    return "\n\n".join(parts) + "\n"


def posix_path(*parts: str) -> str:
    """Join path parts into a normalized posix relative path."""
    return str(PurePosixPath(*parts))
