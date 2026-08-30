import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vanessa.contracts.messages import TaskKind
from vanessa.core.messages import RAG_SOURCE_ROLE, StoredMessage
from vanessa.core.protocols import (
    MessageIndexerProtocol,
    MessageIndexingSchedulerProtocol,
    MessageRepositoryProtocol,
)
from vanessa.infrastructure.broker.dispatcher import TaskDispatcher
from vanessa.infrastructure.db.repository import MessageRepository
from vanessa.pipeline.background import BackgroundExecutor

logger = logging.getLogger(__name__)


class MessageIndexingService(MessageIndexingSchedulerProtocol):
    def __init__(
        self,
        indexer: MessageIndexerProtocol,
        messages: MessageRepositoryProtocol,
        session_factory: async_sessionmaker[AsyncSession],
        max_retries: int = 2,
        background: BackgroundExecutor | None = None,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self._indexer = indexer
        self._messages = messages
        self._session_factory = session_factory
        self._max_retries = max_retries
        self._background = background
        self._dispatcher = dispatcher

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
            except Exception as exc:  # noqa: BLE001
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
        if self._dispatcher is not None:
            # Worker mode: hand the embedding off to the dedicated worker
            # container via the broker (at-least-once on the consumer side).
            self._dispatcher.submit(
                TaskKind.INDEX_MESSAGE,
                {
                    "message_id": record.id,
                    "role": record.role,
                    "content": record.content,
                    "point_id": record.qdrant_point_id,
                },
                dedup_key=f"index:{record.id}",
            )
            return
        if self._background is not None:
            # Bounded background queue: never lets indexing tasks pile up
            # unboundedly and starve the reply path.
            self._background.submit(lambda: self._index_in_background(record))
            return
        asyncio.create_task(self._index_in_background(record))
