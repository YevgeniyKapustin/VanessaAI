"""Knowledge vault storage backends: filesystem and Postgres."""

from __future__ import annotations

import asyncio
import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import Protocol

import yaml

from vanessa.config import settings
from vanessa.knowledge.format import ALL_FOLDERS, INDEX_FILENAME, parse_frontmatter, render_note
from vanessa.knowledge.schema import VaultNote
from vanessa.knowledge.service import KnowledgeService
from vanessa.knowledge.vault_lock import STATE_FILENAME

logger = logging.getLogger(__name__)

_SYNC_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="knowledge-sync")


def run_coro_sync(factory):
    """Run an async factory from sync code, even inside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    return _SYNC_POOL.submit(lambda: asyncio.run(factory())).result()


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


class FilesystemKnowledgeStore:
    def __init__(self, root_path: str | None = None) -> None:
        raw = root_path if root_path is not None else settings.knowledge_path
        self._root = Path(raw.strip()).resolve() if raw and raw.strip() else None
        self._ready = False

    @property
    def is_configured(self) -> bool:
        return self._root is not None

    @property
    def filesystem_root(self) -> Path | None:
        return self._root

    async def ensure_structure(self) -> None:
        if self._root is None:
            return
        await asyncio.to_thread(self._ensure_structure_sync)

    def _ensure_structure_sync(self) -> None:
        assert self._root is not None
        self._root.mkdir(parents=True, exist_ok=True)
        for folder in ALL_FOLDERS:
            folder_path = self._root / folder
            folder_path.mkdir(parents=True, exist_ok=True)
            index_path = folder_path / INDEX_FILENAME
            if not index_path.exists():
                index_path.write_text("", encoding="utf-8")
        self._ready = True

    def _resolve_path(self, relative_path: str) -> Path:
        assert self._root is not None
        parts = PurePosixPath(relative_path).parts
        path = self._root.joinpath(*parts).resolve()
        root_resolved = self._root.resolve()
        if path != root_resolved and root_resolved not in path.parents:
            raise ValueError("path escapes vault root")
        return path

    async def write_note(self, relative_path: str, meta: dict, body: str) -> str:
        return await asyncio.to_thread(self._write_note_sync, relative_path, meta, body)

    def _write_note_sync(self, relative_path: str, meta: dict, body: str) -> str:
        assert self._root is not None
        if not self._ready:
            self._ensure_structure_sync()
        path = self._resolve_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_note(meta, body), encoding="utf-8")
        rel = path.relative_to(self._root).as_posix()
        logger.info("knowledge_note_written path=%s", rel)
        return rel

    async def read_note(self, relative_path: str) -> VaultNote | None:
        return await asyncio.to_thread(self._read_note_sync, relative_path)

    def _read_note_sync(self, relative_path: str) -> VaultNote | None:
        assert self._root is not None
        path = self._resolve_path(relative_path)
        if not path.is_file():
            return None
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        return VaultNote(
            relative_path=path.relative_to(self._root).as_posix(),
            meta=meta,
            body=body,
            updated_at=path.stat().st_mtime,
        )

    async def list_notes(
        self,
        folder: str,
        *,
        recursive: bool = False,
    ) -> list[VaultNote]:
        return await asyncio.to_thread(
            self._list_notes_sync, folder, recursive=recursive
        )

    def list_notes_sync(
        self,
        folder: str,
        *,
        recursive: bool = False,
    ) -> list[VaultNote]:
        return self._list_notes_sync(folder, recursive=recursive)

    def _list_notes_sync(
        self,
        folder: str,
        *,
        recursive: bool = False,
    ) -> list[VaultNote]:
        if self._root is None:
            return []
        folder_path = self._resolve_path(folder) if folder else self._root
        if not folder_path.is_dir():
            return []
        pattern = "**/*.md" if recursive else "*.md"
        notes: list[VaultNote] = []
        for md in sorted(folder_path.glob(pattern)):
            if md.name == INDEX_FILENAME:
                continue
            rel = md.relative_to(self._root).as_posix()
            meta, body = parse_frontmatter(md.read_text(encoding="utf-8"))
            notes.append(
                VaultNote(
                    relative_path=rel,
                    meta=meta,
                    body=body,
                    updated_at=md.stat().st_mtime,
                )
            )
        return notes

    async def notes_signature(self, folder: str) -> tuple:
        return await asyncio.to_thread(self.notes_signature_sync, folder)

    def notes_signature_sync(self, folder: str) -> tuple:
        notes = self._list_notes_sync(folder, recursive=True)
        return tuple((note.relative_path, note.updated_at, len(note.body)) for note in notes)

    async def read_yaml(self, relative_path: str) -> dict:
        return await asyncio.to_thread(self._read_yaml_sync, relative_path)

    def _read_yaml_sync(self, relative_path: str) -> dict:
        assert self._root is not None
        path = self._resolve_path(relative_path)
        if not path.is_file():
            return {}
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return {}
        return data if isinstance(data, dict) else {}

    async def write_yaml(self, relative_path: str, data: dict) -> str:
        return await asyncio.to_thread(self._write_yaml_sync, relative_path, data)

    def _write_yaml_sync(self, relative_path: str, data: dict) -> str:
        assert self._root is not None
        if not self._ready:
            self._ensure_structure_sync()
        path = self._resolve_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip() + "\n",
            encoding="utf-8",
        )
        rel = path.relative_to(self._root).as_posix()
        logger.info("knowledge_yaml_written path=%s", rel)
        return rel

    async def read_state(self) -> dict:
        if self._root is None:
            return {}
        return await self.read_yaml(STATE_FILENAME)

    async def write_state(self, data: dict) -> None:
        if self._root is None:
            return
        await self.write_yaml(STATE_FILENAME, data)

    async def write_attachment(self, relative_path: str, data: bytes) -> str:
        return await asyncio.to_thread(self._write_attachment_sync, relative_path, data)

    def _write_attachment_sync(self, relative_path: str, data: bytes) -> str:
        assert self._root is not None
        if not self._ready:
            self._ensure_structure_sync()
        path = self._resolve_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        rel = path.relative_to(self._root).as_posix()
        logger.info("knowledge_attachment_written path=%s", rel)
        return rel

    async def search_fts(
        self,
        query: str,
        *,
        limit: int = 10,
        node_type: str | None = None,
    ) -> list[VaultNote]:
        del query, limit, node_type
        return []


class PostgresKnowledgeStore:
    def __init__(self, filesystem_root: str | None = None) -> None:
        from vanessa.infrastructure.db.session import async_session_factory

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
