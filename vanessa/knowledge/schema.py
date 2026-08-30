"""Knowledge-vault value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vanessa.core.knowledge_dto import KnowledgeBlock

__all__ = ["KnowledgeBlock", "MemoryPlan", "VaultNote"]


@dataclass(frozen=True, slots=True)
class VaultNote:
    """A single stored note document (path relative to the vault root)."""

    relative_path: str
    meta: dict = field(default_factory=dict)
    body: str = ""
    # Epoch seconds used as a cache key (mtime on disk, updated_at in Postgres).
    updated_at: float = 0.0

    @property
    def note_id(self) -> str:
        value = self.meta.get("id")
        return str(value) if value else ""

    @property
    def note_type(self) -> str:
        value = self.meta.get("type")
        return str(value) if value else ""


@dataclass(frozen=True, slots=True)
class MemoryPlan:
    """Result of the memory decision: a list of raw update dicts to apply."""

    updates: tuple[dict[str, Any], ...] = ()
    weekly_hint: str = ""
