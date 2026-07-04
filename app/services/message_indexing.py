import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.messages import StoredMessage, RAG_SOURCE_ROLE
from app.core.protocols import (
    MessageIndexerProtocol,
    MessageIndexingSchedulerProtocol,
    MessageRepositoryProtocol,
)
from app.db.repository import MessageRepository

logger = logging.getLogger(__name__)


class MessageIndexingService(MessageIndexingSchedulerProtocol):
    def __init__(
        self,
        indexer: MessageIndexerProtocol,
        messages: MessageRepositoryProtocol,
        session_factory: async_sessionmaker[AsyncSession],
        max_retries: int = 2,
    ) -> None:
        self._indexer = indexer
        self._messages = messages
        self._session_factory = session_factory
        self._max_retries = max_retries

    async def _embed_with_retry(self, record: StoredMessage) -> str:
        if record.role != RAG_SOURCE_ROLE:
            return record.qdrant_point_id or ""
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._indexer.index(
                    message_id=record.id,
                    role=record.role,
                    content=record.content,
                    point_id=record.qdrant_point_id,
                )
            except Exception as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                await asyncio.sleep(0.5 * (attempt + 1))
        assert last_error is not None
        raise last_error

    async def index_now(self, record: StoredMessage) -> None:
        if record.role != RAG_SOURCE_ROLE:
            return
        try:
            point_id = await self._embed_with_retry(record)
            await self._messages.update_qdrant_point_id(record.id, point_id)
        except Exception:
            logger.exception("Indexing failed for message %s", record.id)

    async def _index_in_background(self, record: StoredMessage) -> None:
        try:
            point_id = await self._embed_with_retry(record)
            async with self._session_factory() as session:
                repo = MessageRepository(session)
                await repo.update_qdrant_point_id(record.id, point_id)
                await session.commit()
        except Exception:
            logger.exception("Background indexing failed for message %s", record.id)

    def schedule(self, record: StoredMessage) -> None:
        if record.role != RAG_SOURCE_ROLE:
            return
        asyncio.create_task(self._index_in_background(record))
