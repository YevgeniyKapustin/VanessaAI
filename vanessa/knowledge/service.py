"""KnowledgeService: atomic upsert/read/search over knowledge_nodes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from vanessa.infrastructure.db.models import KnowledgeDocument, KnowledgeNodeRow
from vanessa.knowledge.node import (
    KnowledgeNode,
    node_to_note,
    note_to_node,
    note_to_row_values,
    row_to_note,
)
from vanessa.knowledge.schema import VaultNote


class KnowledgeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, node_id: str) -> KnowledgeNode | None:
        row = await self._session.get(KnowledgeNodeRow, node_id)
        if row is None:
            return None
        return note_to_node(row_to_note(row))

    async def get_note(self, relative_path: str) -> VaultNote | None:
        row = await self._session.get(KnowledgeNodeRow, relative_path)
        if row is None:
            return None
        return row_to_note(row)

    async def upsert(self, node: KnowledgeNode) -> KnowledgeNode:
        note = await self.upsert_note_doc(node_to_note(node))
        return note_to_node(note)

    async def upsert_note_doc(self, note: VaultNote) -> VaultNote:
        values = note_to_row_values(note)
        now = datetime.now(UTC)
        existing = await self._session.get(KnowledgeNodeRow, values["id"])
        created_at = existing.created_at if existing is not None else now
        insert_values = {
            "id": values["id"],
            "folder": values["folder"],
            "slug": values["slug"],
            "type": values["type"],
            "title": values["title"],
            "aliases": values["aliases"],
            "metadata": values["metadata"],
            "content": values["content"],
            "source_message_ids": values["source_message_ids"],
            "created_at": created_at,
            "updated_at": now,
        }
        stmt = insert(KnowledgeNodeRow.__table__).values(**insert_values)
        update_cols = {
            key: stmt.excluded[key]
            for key in insert_values
            if key not in {"id", "created_at"}
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_=update_cols,
        )
        await self._session.execute(stmt)
        await self._session.flush()
        stored = await self._session.get(KnowledgeNodeRow, values["id"])
        assert stored is not None
        return row_to_note(stored)

    async def list_notes(
        self,
        folder: str,
        *,
        recursive: bool = False,
    ) -> list[VaultNote]:
        stmt = select(KnowledgeNodeRow)
        if recursive:
            prefix = folder.rstrip("/")
            stmt = stmt.where(
                (KnowledgeNodeRow.folder == prefix)
                | KnowledgeNodeRow.folder.startswith(prefix + "/")
            )
        else:
            stmt = stmt.where(KnowledgeNodeRow.folder == folder.rstrip("/"))
        stmt = stmt.order_by(KnowledgeNodeRow.id)
        result = await self._session.execute(stmt)
        return [row_to_note(row) for row in result.scalars().all()]

    async def search_fts(
        self,
        query: str,
        *,
        limit: int = 10,
        node_type: str | None = None,
    ) -> list[VaultNote]:
        cleaned = query.strip()
        if not cleaned:
            return []
        ts_query = func.plainto_tsquery("simple", cleaned)
        stmt = (
            select(KnowledgeNodeRow)
            .where(KnowledgeNodeRow.search_vector.op("@@")(ts_query))
            .order_by(func.ts_rank(KnowledgeNodeRow.search_vector, ts_query).desc())
            .limit(limit)
        )
        if node_type:
            stmt = stmt.where(KnowledgeNodeRow.type == node_type)
        result = await self._session.execute(stmt)
        return [row_to_note(row) for row in result.scalars().all()]

    async def search_aliases(self, query: str, *, limit: int = 10) -> list[VaultNote]:
        needle = query.strip().lower()
        if not needle:
            return []
        stmt = (
            select(KnowledgeNodeRow)
            .where(
                func.lower(func.array_to_string(KnowledgeNodeRow.aliases, " ")).like(
                    f"%{needle}%"
                )
            )
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [row_to_note(row) for row in result.scalars().all()]

    async def notes_signature(self, folder: str) -> tuple:
        prefix = folder.rstrip("/")
        stmt = select(
            KnowledgeNodeRow.id,
            KnowledgeNodeRow.updated_at,
        ).where(
            (KnowledgeNodeRow.folder == prefix)
            | KnowledgeNodeRow.folder.startswith(prefix + "/")
        )
        result = await self._session.execute(stmt)
        return tuple(
            (node_id, ts.timestamp() if ts is not None else 0.0)
            for node_id, ts in result.all()
        )

    async def read_document(self, path: str) -> dict[str, Any]:
        row = await self._session.get(KnowledgeDocument, path)
        if row is None or not isinstance(row.data, dict):
            return {}
        return dict(row.data)

    async def write_document(self, path: str, data: dict[str, Any]) -> str:
        now = datetime.now(UTC)
        stmt = insert(KnowledgeDocument).values(path=path, data=data, updated_at=now)
        stmt = stmt.on_conflict_do_update(
            index_elements=["path"],
            set_={"data": stmt.excluded.data, "updated_at": now},
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return path


