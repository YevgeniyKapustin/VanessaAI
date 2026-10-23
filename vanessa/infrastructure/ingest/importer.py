from __future__ import annotations

import logging
from collections.abc import Iterable

from vanessa.core.messages import StoredMessage
from vanessa.core.protocols import MessageRepositoryProtocol, UnitOfWorkProtocol
from vanessa.infrastructure.db.repository import UserRepository
from vanessa.infrastructure.ingest.telegram_export import ParsedExportMessage

logger = logging.getLogger(__name__)


class HistoryImporter:
    def __init__(
        self,
        *,
        messages: MessageRepositoryProtocol,
        users: UserRepository,
        unit_of_work: UnitOfWorkProtocol,
        batch_size: int = 64,
    ) -> None:
        self._messages = messages
        self._users = users
        self._uow = unit_of_work
        self._batch_size = batch_size

    async def import_messages(
        self,
        parsed_messages: Iterable[ParsedExportMessage],
    ) -> tuple[int, int]:
        imported = 0
        skipped = 0
        batch: list[ParsedExportMessage] = []

        for message in parsed_messages:
            batch.append(message)
            if len(batch) >= self._batch_size:
                imported, skipped = await self._flush_batch(
                    batch, imported, skipped
                )

        return await self._flush_batch(batch, imported, skipped)

    async def _take_pending(
        self, batch: list[ParsedExportMessage]
    ) -> tuple[list[ParsedExportMessage], int]:
        telegram_ids = [item.telegram_message_id for item in batch]
        existing = await self._messages.get_existing_telegram_message_ids(
            telegram_ids,
        )
        pending = [
            item for item in batch if item.telegram_message_id not in existing
        ]
        skipped_count = len(batch) - len(pending)
        batch.clear()
        return pending, skipped_count

    async def _ensure_sender(self, item: ParsedExportMessage) -> None:
        if item.sender_telegram_id is None:
            return
        await self._users.get_or_create(
            telegram_id=item.sender_telegram_id,
            first_name=item.sender_display_name,
        )

    async def _store_pending(
        self, pending: list[ParsedExportMessage]
    ) -> list[StoredMessage]:
        stored: list[StoredMessage] = []
        for item in pending:
            await self._ensure_sender(item)
            message = await self._messages.create(
                role="user",
                content=item.content,
                sender_telegram_id=item.sender_telegram_id,
                created_at=item.created_at,
                telegram_message_id=item.telegram_message_id,
            )
            stored.append(message)
        return stored

    async def _flush_batch(
        self,
        batch: list[ParsedExportMessage],
        imported: int,
        skipped: int,
    ) -> tuple[int, int]:
        if not batch:
            return imported, skipped

        pending, extra_skipped = await self._take_pending(batch)
        skipped += extra_skipped
        if not pending:
            return imported, skipped

        stored = await self._store_pending(pending)

        await self._uow.commit()
        imported += len(stored)
        logger.info(
            "Imported %s messages (%s skipped so far)",
            imported,
            skipped,
        )
        return imported, skipped
