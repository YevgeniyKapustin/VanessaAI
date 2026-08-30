"""KnowledgeVault: machine-only structured notes storage.

Public facade over a storage backend (filesystem or Postgres). File IO and
SQL writes are serialized with a module-level asyncio lock so concurrent
writers never interleave. Callers keep speaking relative paths + frontmatter.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from vanessa.knowledge.schema import VaultNote
from vanessa.knowledge.store import KnowledgeStore, build_knowledge_store
from vanessa.knowledge.vault_lock import VAULT_LOCK

logger = logging.getLogger(__name__)


class KnowledgeVault:
    def __init__(
        self,
        root_path: str | None = None,
        *,
        store: KnowledgeStore | None = None,
    ) -> None:
        self._store = build_knowledge_store(root_path, store)
        self._lock = VAULT_LOCK

    @property
    def is_configured(self) -> bool:
        return self._store.is_configured

    @property
    def root(self) -> Path | None:
        return self._store.filesystem_root

    async def ensure_structure(self) -> None:
        if not self.is_configured:
            return
        async with self._lock:
            await self._store.ensure_structure()

    async def write_note(
        self,
        relative_path: str,
        meta: dict,
        body: str,
        *,
        mutation_source: str = "direct",
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("knowledge vault is not configured")
        started = time.perf_counter()
        async with self._lock:
            existing = await self._store.read_note(relative_path)
            rel = await self._store.write_note(relative_path, meta, body)
        duration_ms = (time.perf_counter() - started) * 1000
        action = "update" if existing else "create"
        node_type = str(meta.get("type") or "note")
        from vanessa.infrastructure.observability.metrics import record_knowledge_mutation

        record_knowledge_mutation(node_type, action)
        logger.info(
            "knowledge_node_updated",
            extra={
                "event": "knowledge_node_updated",
                "node_id": rel,
                "node_type": node_type,
                "mutation_source": mutation_source,
                "duration_ms": round(duration_ms, 1),
            },
        )
        return rel

    async def read_yaml(self, relative_path: str) -> dict:
        if not self.is_configured:
            return {}
        async with self._lock:
            return await self._store.read_yaml(relative_path)

    async def write_yaml(self, relative_path: str, data: dict) -> str:
        if not self.is_configured:
            raise RuntimeError("knowledge vault is not configured")
        async with self._lock:
            return await self._store.write_yaml(relative_path, data)

    async def write_attachment(self, relative_path: str, data: bytes) -> str:
        if not self.is_configured:
            raise RuntimeError("knowledge vault is not configured")
        async with self._lock:
            return await self._store.write_attachment(relative_path, data)

    async def read_state(self) -> dict:
        if not self.is_configured:
            return {}
        async with self._lock:
            return await self._store.read_state()

    async def write_state(self, data: dict) -> None:
        if not self.is_configured:
            return
        async with self._lock:
            await self._store.write_state(data)

    async def read_note(self, relative_path: str) -> VaultNote | None:
        if not self.is_configured:
            return None
        return await self._store.read_note(relative_path)

    async def list_notes(
        self,
        folder: str,
        *,
        recursive: bool = False,
    ) -> list[VaultNote]:
        if not self.is_configured:
            return []
        return await self._store.list_notes(folder, recursive=recursive)

    def list_notes_sync(
        self,
        folder: str,
        *,
        recursive: bool = False,
    ) -> list[VaultNote]:
        if not self.is_configured:
            return []
        return self._store.list_notes_sync(folder, recursive=recursive)

    async def notes_signature(self, folder: str) -> tuple:
        if not self.is_configured:
            return ()
        return await self._store.notes_signature(folder)

    def notes_signature_sync(self, folder: str) -> tuple:
        if not self.is_configured:
            return ()
        return self._store.notes_signature_sync(folder)

    async def search_fts(
        self,
        query: str,
        *,
        limit: int = 10,
        node_type: str | None = None,
    ) -> list[VaultNote]:
        if not self.is_configured:
            return []
        return await self._store.search_fts(query, limit=limit, node_type=node_type)
