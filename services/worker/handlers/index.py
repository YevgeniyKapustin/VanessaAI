"""Qdrant indexing handler for a single chat message."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from vanessa.contracts.messages import TaskMessage
from vanessa.core.messages import RAG_SOURCE_ROLE
from vanessa.infrastructure.db import repository

logger = logging.getLogger(__name__)


class IndexMessageHandler:
    """Embed a single message into Qdrant and persist the point id.

    Mirrors ``HybridSearchService.index`` (embed → upsert) without needing a
    message repository, and updates the message's stored point id afterwards.
    """

    def __init__(
        self,
        embeddings,
        vector_store,
        session_factory,
        *,
        max_retries: int = 2,
    ) -> None:
        self._embeddings = embeddings
        self._vector_store = vector_store
        self._session_factory = session_factory
        self._max_retries = max_retries

    async def handle(self, task: TaskMessage) -> None:
        payload = task.payload
        message_id = int(payload.get("message_id") or 0)
        role = str(payload.get("role") or "")
        content = str(payload.get("content") or "")
        point_id = payload.get("point_id")
        try:
            point = await self._index_with_retry(
                message_id, role, content, point_id
            )
        except Exception:
            logger.exception("worker_index_failed message_id=%s", message_id)
            return
        try:
            async with self._session_factory() as session:
                await repository.MessageRepository(session).update_qdrant_point_id(
                    message_id, point
                )
                await session.commit()
        except Exception:
            logger.exception(
                "worker_index_update_failed message_id=%s", message_id
            )

    async def _index_with_retry(
        self, message_id: int, role: str, content: str, point_id: Any
    ) -> str:
        if role != RAG_SOURCE_ROLE:
            return point_id or ""
        return await self._upsert_with_retries(
            message_id, role, content, point_id
        )

    async def _upsert_with_retries(
        self, message_id: int, role: str, content: str, point_id: Any
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._upsert_once(
                    message_id, role, content, point_id
                )
            except Exception as exc:  # noqa: BLE001 - retry any embed/upsert failure
                last_error = exc
            if not await self._should_retry(attempt):
                break
        assert last_error is not None
        raise last_error

    async def _upsert_once(
        self, message_id: int, role: str, content: str, point_id: Any
    ) -> str:
        vector = await self._embeddings.embed(content)
        return await self._vector_store.upsert_message(
            message_id=message_id,
            role=role,
            content=content,
            vector=vector,
            point_id=point_id,
        )

    async def _should_retry(self, attempt: int) -> bool:
        if attempt >= self._max_retries:
            return False
        await asyncio.sleep(0.5 * (attempt + 1))
        return True
