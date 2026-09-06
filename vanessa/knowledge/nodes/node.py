"""Knowledge-node contract: Pydantic schema and VaultNote <-> row mapping.

The vault still speaks ``VaultNote`` (relative path + frontmatter + markdown
body). Postgres stores the same document as a relational-document row: typed
columns for search, JSONB for the remaining frontmatter.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from vanessa.knowledge.format import today
from vanessa.knowledge.nodes.node_convert import as_int_list, parse_date, row_to_note
from vanessa.knowledge.nodes.node_schema import (
    NODE_TYPES,
    KnowledgeNode,
    extra_metadata,
    folder_of,
    slug_of,
    type_of,
)
from vanessa.knowledge.schema import VaultNote

__all__ = [
    "NODE_TYPES",
    "KnowledgeNode",
    "extra_metadata",
    "folder_of",
    "node_to_note",
    "note_to_node",
    "note_to_row_values",
    "row_to_note",
    "slug_of",
    "type_of",
]


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def note_to_row_values(note: VaultNote) -> dict[str, Any]:
    """Flatten a vault note into ``knowledge_nodes`` column values."""
    meta = dict(note.meta or {})
    fallback = date.fromisoformat(today())
    created = parse_date(meta.get("created"), fallback)
    updated = parse_date(meta.get("updated"), fallback)
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
        "source_message_ids": as_int_list(meta.get("source_message_ids")),
        "created_at": datetime(created.year, created.month, created.day, tzinfo=UTC),
        "updated_at": datetime(updated.year, updated.month, updated.day, tzinfo=UTC),
    }


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
