"""Knowledge vault storage backends: filesystem and Postgres."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from vanessa.config import settings
from vanessa.knowledge.schema import VaultNote
from vanessa.knowledge.store.store_fs import FilesystemKnowledgeStore
from vanessa.knowledge.store.store_postgres import PostgresKnowledgeStore, run_coro_sync

__all__ = [
    "FilesystemKnowledgeStore",
    "KnowledgeStore",
    "PostgresKnowledgeStore",
    "build_knowledge_store",
    "run_coro_sync",
]


class KnowledgeStore(Protocol):
    is_configured: bool
    filesystem_root: Path | None

    async def ensure_structure(self) -> None: ...

    async def write_note(self, relative_path: str, meta: dict, body: str) -> str: ...

    async def read_note(self, relative_path: str) -> VaultNote | None: ...

    async def list_notes(
        self,
        folder: str,
        *,
        recursive: bool = False,
    ) -> list[VaultNote]: ...

    def list_notes_sync(
        self,
        folder: str,
        *,
        recursive: bool = False,
    ) -> list[VaultNote]: ...

    async def notes_signature(self, folder: str) -> tuple: ...

    def notes_signature_sync(self, folder: str) -> tuple: ...

    async def read_yaml(self, relative_path: str) -> dict: ...

    async def write_yaml(self, relative_path: str, data: dict) -> str: ...

    async def read_state(self) -> dict: ...

    async def write_state(self, data: dict) -> None: ...

    async def write_attachment(self, relative_path: str, data: bytes) -> str: ...

    async def search_fts(
        self,
        query: str,
        *,
        limit: int = 10,
        node_type: str | None = None,
    ) -> list[VaultNote]: ...


def build_knowledge_store(
    root_path: str | None = None,
    store: KnowledgeStore | None = None,
) -> KnowledgeStore:
    if store is not None:
        return store
    if root_path is not None:
        return FilesystemKnowledgeStore(root_path)
    backend = (settings.knowledge_store or "filesystem").strip().lower()
    if backend == "postgres":
        return PostgresKnowledgeStore()
    return FilesystemKnowledgeStore()
