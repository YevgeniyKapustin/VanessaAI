from __future__ import annotations

import logging
from collections.abc import Iterable

from app.core.protocols import (
    EmbeddingProviderProtocol,
    MessageRepositoryProtocol,
    UnitOfWorkProtocol,
    VectorStoreProtocol,
)
from app.core.messages import StoredMessage
from app.db.repository import UserRepository
from app.ingest.telegram_export import ParsedExportMessage

logger = logging.getLogger(__name__)


class HistoryImporter:
    def __init__(
        self,
        messages: MessageRepositoryProtocol,
        users: UserRepository,
        embeddings: EmbeddingProviderProtocol,
        vector_store: VectorStoreProtocol,
        unit_of_work: UnitOfWorkProtocol,
        batch_size: int = 64,
    ) -> None:
        self._messages = messages
        self._users = users
        self._embeddings = embeddings
        self._vector_store = vector_store
        self._uow = unit_of_work
        self._batch_size = batch_size

    async def import_messages(
        self,
        parsed_messages: Iterable[ParsedExportMessage],
        embed: bool = True,
    ) -> tuple[int, int]:
        await self._vector_store.ensure_collection()

        imported = 0
        skipped = 0
        batch: list[ParsedExportMessage] = []

        async def flush_batch() -> None:
            nonlocal imported, skipped
            if not batch:
                return

            telegram_ids = [item.telegram_message_id for item in batch]
            existing = await self._messages.get_existing_telegram_message_ids(
                telegram_ids,
            )
            pending = [
                item for item in batch if item.telegram_message_id not in existing
            ]
            skipped += len(batch) - len(pending)
            batch.clear()

            if not pending:
                return

            stored: list[StoredMessage] = []
            for item in pending:
                if item.sender_telegram_id is not None:
                    await self._users.get_or_create(
                        telegram_id=item.sender_telegram_id,
                        first_name=item.sender_display_name,
                    )
                message = await self._messages.create(
                    role="user",
                    content=item.content,
                    sender_telegram_id=item.sender_telegram_id,
                    created_at=item.created_at,
                    telegram_message_id=item.telegram_message_id,
                )
                stored.append(message)

            if embed:
                vectors = await self._embeddings.embed_batch(
                    [message.content for message in stored]
                )
                point_ids = await self._vector_store.upsert_batch(
                    [
                        (message.id, vector, message.qdrant_point_id)
                        for message, vector in zip(stored, vectors, strict=True)
                    ],
                )
                for message, point_id in zip(stored, point_ids, strict=True):
                    await self._messages.update_qdrant_point_id(
                        message.id,
                        point_id,
                    )

            await self._uow.commit()
            imported += len(stored)
            logger.info(
                "Imported %s messages (%s skipped so far)",
                imported,
                skipped,
            )

        for message in parsed_messages:
            batch.append(message)
            if len(batch) >= self._batch_size:
                await flush_batch()

        await flush_batch()
        return imported, skipped
