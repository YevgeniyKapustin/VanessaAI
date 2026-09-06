"""Postgres backend for the knowledge vault."""

from __future__ import annotations

import asyncio
import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from vanessa.knowledge.nodes.service import KnowledgeService
from vanessa.knowledge.schema import VaultNote
from vanessa.knowledge.store.store_fs import FilesystemKnowledgeStore
from vanessa.knowledge.store.vault_lock import STATE_FILENAME

logger = logging.getLogger(__name__)

_SYNC_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="knowledge-sync")


def run_coro_sync(factory):
    """Run an async factory from sync code, even inside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    return _SYNC_POOL.submit(lambda: asyncio.run(factory())).result()


class PostgresKnowledgeStore:
    def __init__(self, filesystem_root: str | None = None) -> None:
        from vanessa.infrastructure.db.session import (  # noqa: PLC0415
            async_session_factory,
        )

        self._factory = async_session_factory
        raw = (filesystem_root or "").strip()
        self._root = Path(raw).resolve() if raw else None
        self._files = (
            FilesystemKnowledgeStore(str(self._root))
            if self._root is not None
            else None
        )

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def filesystem_root(self) -> Path | None:
        return self._root

    async def ensure_structure(self) -> None:
        return None

    async def write_note(self, relative_path: str, meta: dict, body: str) -> str:
        note = VaultNote(
            relative_path=relative_path.replace("\\", "/"),
            meta=meta,
            body=body,
        )
        async with self._factory() as session:
            service = KnowledgeService(session)
            stored = await service.upsert_note_doc(note)
            await session.commit()
        logger.info("knowledge_note_written path=%s store=postgres", stored.relative_path)
        return stored.relative_path

    async def read_note(self, relative_path: str) -> VaultNote | None:
        async with self._factory() as session:
            return await KnowledgeService(session).get_note(
                relative_path.replace("\\", "/")
            )

    async def list_notes(
        self,
        folder: str,
        *,
        recursive: bool = False,
    ) -> list[VaultNote]:
        async with self._factory() as session:
            return await KnowledgeService(session).list_notes(
                folder, recursive=recursive
            )

    def list_notes_sync(
        self,
        folder: str,
        *,
        recursive: bool = False,
    ) -> list[VaultNote]:
        return run_coro_sync(lambda: self.list_notes(folder, recursive=recursive))

    async def notes_signature(self, folder: str) -> tuple:
        async with self._factory() as session:
            return await KnowledgeService(session).notes_signature(folder)

    def notes_signature_sync(self, folder: str) -> tuple:
        return run_coro_sync(lambda: self.notes_signature(folder))

    async def read_yaml(self, relative_path: str) -> dict:
        async with self._factory() as session:
            return await KnowledgeService(session).read_document(relative_path)

    async def write_yaml(self, relative_path: str, data: dict) -> str:
        async with self._factory() as session:
            path = await KnowledgeService(session).write_document(relative_path, data)
            await session.commit()
        logger.info("knowledge_yaml_written path=%s store=postgres", path)
        return path

    async def read_state(self) -> dict:
        return await self.read_yaml(STATE_FILENAME)

    async def write_state(self, data: dict) -> None:
        await self.write_yaml(STATE_FILENAME, data)

    async def write_attachment(self, relative_path: str, data: bytes) -> str:
        if self._files is not None:
            return await self._files.write_attachment(relative_path, data)
        payload = {
            "encoding": "base64",
            "bytes": base64.b64encode(data).decode("ascii"),
        }
        async with self._factory() as session:
            path = await KnowledgeService(session).write_document(
                relative_path, payload
            )
            await session.commit()
        logger.info(
            "knowledge_attachment_written path=%s store=postgres", path
        )
        return path

    async def search_fts(
        self,
        query: str,
        *,
        limit: int = 10,
        node_type: str | None = None,
    ) -> list[VaultNote]:
        async with self._factory() as session:
            return await KnowledgeService(session).search_fts(
                query, limit=limit, node_type=node_type
            )
