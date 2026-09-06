"""Filesystem backend for the knowledge vault."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import yaml

from vanessa.config import settings
from vanessa.knowledge.format import (
    ALL_FOLDERS,
    INDEX_FILENAME,
    parse_frontmatter,
    render_note,
)
from vanessa.knowledge.schema import VaultNote
from vanessa.knowledge.store.store_paths import list_markdown_notes, resolve_vault_path
from vanessa.knowledge.store.vault_lock import STATE_FILENAME

logger = logging.getLogger(__name__)


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
        return resolve_vault_path(self._root, relative_path)

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
        return list_markdown_notes(self._root, folder, recursive=recursive)

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
