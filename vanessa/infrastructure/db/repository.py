from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from vanessa.core.messages import RAG_SOURCE_ROLE, StoredMessage
from vanessa.infrastructure.db import message_queries, message_windows
from vanessa.infrastructure.db.mappers import message_to_stored
from vanessa.infrastructure.db.models import Message
from vanessa.infrastructure.db.user_repository import UserRepository

__all__ = ["MessageRepository", "UserRepository"]


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def _savepoint(self):
        """Run a fallible DB read inside a SAVEPOINT.

        Pipeline stages treat some reads as optional/fail-open (the photo-album
        search, the RAG helpers) and swallow their errors. Without a savepoint,
        a swallowed read failure aborts the whole Postgres transaction, and the
        next statement on the same request-scoped session — typically the
        assistant-message INSERT — fails with ``InFailedSQLTransactionError``.
        ``begin_nested`` rolls back to the savepoint on error, leaving the outer
        transaction usable, then re-raises so the caller's fail-open handler
        still decides what to do.
        """
        async with self._session.begin_nested():
            yield

    async def create(
        self,
        role: str,
        content: str,
        sender_telegram_id: int | None = None,
        qdrant_point_id: str | None = None,
        created_at: datetime | None = None,
        telegram_message_id: int | None = None,
        reply_to_message_id: int | None = None,
        reply_to_text: str | None = None,
        reply_to_sender_telegram_id: int | None = None,
        reply_to_sender_name: str | None = None,
        attachments: list[dict] | None = None,
    ) -> StoredMessage:
        message = Message(
            sender_telegram_id=sender_telegram_id,
            telegram_message_id=telegram_message_id,
            role=role,
            content=content,
            qdrant_point_id=qdrant_point_id,
            reply_to_message_id=reply_to_message_id,
            reply_to_text=reply_to_text,
            reply_to_sender_telegram_id=reply_to_sender_telegram_id,
            reply_to_sender_name=reply_to_sender_name,
            attachments=attachments,
        )
        if created_at is not None:
            message.created_at = created_at
        self._session.add(message)
        await self._session.flush()
        if role == RAG_SOURCE_ROLE:
            await self._session.execute(
                text(
                    "UPDATE messages SET search_vector = "
                    "to_tsvector('russian', :content) WHERE id = :id"
                ),
                {"content": content, "id": message.id},
            )
        return message_to_stored(message)

    async def get_existing_telegram_message_ids(
        self,
        telegram_message_ids: list[int],
    ) -> set[int]:
        if not telegram_message_ids:
            return set()
        result = await self._session.execute(
            select(Message.telegram_message_id).where(
                Message.telegram_message_id.in_(telegram_message_ids),
            )
        )
        return {row[0] for row in result.all() if row[0] is not None}

    async def get_by_id(self, message_id: int) -> StoredMessage | None:
        result = await self._session.execute(
            select(Message).where(Message.id == message_id)
        )
        message = result.scalar_one_or_none()
        if message is None:
            return None
        return message_to_stored(message)

    async def get_distinct_sender_telegram_ids(self) -> list[int]:
        result = await self._session.execute(
            text(
                """
                SELECT DISTINCT sender_telegram_id
                FROM messages
                WHERE sender_telegram_id IS NOT NULL
                ORDER BY sender_telegram_id
                """
            )
        )
        return [row[0] for row in result.all()]

    async def get_by_ids(self, message_ids: list[int]) -> list[StoredMessage]:
        if not message_ids:
            return []
        result = await self._session.execute(
            select(Message).where(Message.id.in_(message_ids))
        )
        messages = {
            message.id: message_to_stored(message)
            for message in result.scalars().all()
        }
        return [messages[mid] for mid in message_ids if mid in messages]

    async def update_photo_caption(
        self,
        message_id: int,
        caption: str,
    ) -> None:
        """Persist the generated caption of a photo message.

        The FTS ``search_vector`` is recomputed to include the caption, so a bare
        photo becomes findable "by meaning" in the text/hybrid RAG.
        """
        await self._session.execute(
            text(
                "UPDATE messages "
                "SET photo_caption = :caption, "
                "    search_vector = to_tsvector('russian', content || ' ' || :caption) "
                "WHERE id = :message_id AND role = 'user'"
            ),
            {"caption": caption, "message_id": message_id},
        )

    async def update_qdrant_point_id(
        self,
        message_id: int,
        point_id: str,
    ) -> None:
        # Also guarded by a savepoint: ``index_now`` swallows failures here, and
        # a poisoned transaction would silently break the later assistant INSERT.
        async with self._savepoint():
            message = await self._session.get(Message, message_id)
            if message is None:
                return
            message.qdrant_point_id = point_id

    get_recent = message_queries.get_recent
    get_newer_than = message_queries.get_newer_than
    get_messages_since = message_queries.get_messages_since
    count_newer_than = message_queries.count_newer_than
    fulltext_search = message_queries.fulltext_search
    search_photo_messages = message_queries.search_photo_messages
    _window_for_anchor = message_windows._window_for_anchor
    get_conversation_window_blocks = message_windows.get_conversation_window_blocks
