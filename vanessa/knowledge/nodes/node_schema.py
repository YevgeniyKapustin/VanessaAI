"""Knowledge-node schema and path/type helpers."""

from __future__ import annotations

from datetime import date
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Frontmatter keys that are denormalized into columns (not only JSONB).
COLUMN_KEYS = frozenset(
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
FOLDER_TYPES = {
    "People": "person",
    "Lore/glossary": "glossary",
    "Lore/events": "event",
}


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


_PREFIX_TYPES = (
    ("_archive", "archive"),
    ("Culture/", "recommendation"),
    ("Logs/", "log"),
)


def _type_from_prefix(folder: str) -> str:
    for prefix, node_type in _PREFIX_TYPES:
        if folder.startswith(prefix):
            return node_type
    return "note"


def _type_from_folder(folder: str) -> str:
    mapped = FOLDER_TYPES.get(folder)
    if mapped:
        return mapped
    return _type_from_prefix(folder)


def type_of(relative_path: str, meta: dict[str, Any]) -> str:
    value = str(meta.get("type") or "").strip()
    if value in NODE_TYPES:
        return value
    return _type_from_folder(folder_of(relative_path))


def extra_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in meta.items() if key not in COLUMN_KEYS}
