"""Knowledge-node contract: Pydantic schema and VaultNote <-> row mapping.

The vault still speaks ``VaultNote`` (relative path + frontmatter + markdown
body). Postgres stores the same document as a relational-document row: typed
columns for search, JSONB for the remaining frontmatter.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from vanessa.knowledge.format import today
from vanessa.knowledge.schema import VaultNote

# Frontmatter keys that are denormalized into columns (not only JSONB).
_COLUMN_KEYS = frozenset(
    {
        "id",
        "type",
        "title",
        "aliases",
        "created",
        "updated",
        "source_message_ids",
    }
)

NODE_TYPES = (
    "person",
    "glossary",
    "event",
    "recommendation",
    "log",
    "note",
    "archive",
)


class KnowledgeNode(BaseModel):
    """API / DB contract for one knowledge-vault document."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: str
    title: str | None = None
    aliases: list[str] = Field(default_factory=list)
    created: date
    updated: date
    metadata_fields: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    content: str
    source_message_ids: list[int] = Field(default_factory=list)
    slug: str = ""

    @property
    def relative_path(self) -> str:
        return self.id


def folder_of(relative_path: str) -> str:
    posix = relative_path.replace("\\", "/").strip("/")
    if "/" not in posix:
        return ""
    return posix.rsplit("/", 1)[0]


def slug_of(relative_path: str, meta: dict[str, Any]) -> str:
    value = meta.get("id")
    if value:
        return str(value)
    return PurePosixPath(relative_path).stem


def type_of(relative_path: str, meta: dict[str, Any]) -> str:
    value = str(meta.get("type") or "").strip()
    if value in NODE_TYPES:
        return value
    folder = folder_of(relative_path)
    if folder == "People" or folder.startswith("_archive"):
        return "person" if folder == "People" else "archive"
    if folder == "Lore/glossary":
        return "glossary"
    if folder == "Lore/events":
        return "event"
    if folder.startswith("Culture/"):
        return "recommendation"
    if folder.startswith("Logs/"):
        return "log"
    return "note"


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _as_int_list(value: object) -> list[int]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = [value]
    result: list[int] = []
    seen: set[int] = set()
    for item in items:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number not in seen:
            seen.add(number)
            result.append(number)
    return result


def _parse_date(value: object, fallback: date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return fallback


def extra_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in meta.items() if key not in _COLUMN_KEYS}


def note_to_row_values(note: VaultNote) -> dict[str, Any]:
    """Flatten a vault note into ``knowledge_nodes`` column values."""
    meta = dict(note.meta or {})
    fallback = date.fromisoformat(today())
    created = _parse_date(meta.get("created"), fallback)
    updated = _parse_date(meta.get("updated"), fallback)
    return {
        "id": note.relative_path.replace("\\", "/"),
        "folder": folder_of(note.relative_path),
        "slug": slug_of(note.relative_path, meta),
        "type": type_of(note.relative_path, meta),
        "title": str(meta["title"]).strip() if meta.get("title") else None,
        "aliases": _as_str_list(
            list(meta.get("aliases") or []) + list(meta.get("names") or [])
        ),
        "metadata": extra_metadata(meta),
        "content": note.body or "",
        "source_message_ids": _as_int_list(meta.get("source_message_ids")),
        "created_at": datetime(created.year, created.month, created.day, tzinfo=UTC),
        "updated_at": datetime(updated.year, updated.month, updated.day, tzinfo=UTC),
    }


def row_to_note(row: Any) -> VaultNote:
    """Rebuild a ``VaultNote`` from a ``knowledge_nodes`` row."""
    extra = dict(getattr(row, "metadata_", None) or {})
    slug = str(getattr(row, "slug", None) or PurePosixPath(row.id).stem)
    node_type = str(getattr(row, "type", None) or "note")
    meta: dict[str, Any] = {**extra, "id": slug, "type": node_type}
    title = getattr(row, "title", None)
    if title:
        meta["title"] = title
    aliases = list(getattr(row, "aliases", None) or [])
    if aliases:
        meta["aliases"] = aliases
    sources = list(getattr(row, "source_message_ids", None) or [])
    if sources:
        meta["source_message_ids"] = [int(item) for item in sources]
    created_at = getattr(row, "created_at", None)
    updated_at = getattr(row, "updated_at", None)
    if created_at is not None:
        meta["created"] = created_at.date().isoformat()
    if updated_at is not None:
        meta["updated"] = updated_at.date().isoformat()
    epoch = updated_at.timestamp() if updated_at is not None else 0.0
    return VaultNote(
        relative_path=str(row.id),
        meta=meta,
        body=str(getattr(row, "content", None) or ""),
        updated_at=epoch,
    )


def note_to_node(note: VaultNote) -> KnowledgeNode:
    values = note_to_row_values(note)
    return KnowledgeNode(
        id=values["id"],
        type=values["type"],
        title=values["title"],
        aliases=values["aliases"],
        created=values["created_at"].date(),
        updated=values["updated_at"].date(),
        metadata=values["metadata"],
        content=values["content"],
        source_message_ids=values["source_message_ids"],
        slug=values["slug"],
    )


def node_to_note(node: KnowledgeNode) -> VaultNote:
    meta: dict[str, Any] = {
        **node.metadata_fields,
        "id": node.slug or slug_of(node.id, {}),
        "type": node.type,
        "created": node.created.isoformat(),
        "updated": node.updated.isoformat(),
    }
    if node.title:
        meta["title"] = node.title
    if node.aliases:
        meta["aliases"] = list(node.aliases)
    if node.source_message_ids:
        meta["source_message_ids"] = list(node.source_message_ids)
    return VaultNote(relative_path=node.id, meta=meta, body=node.content)
