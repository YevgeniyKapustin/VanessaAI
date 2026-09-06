from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text

from vanessa.core.messages import RAG_SOURCE_ROLE, StoredMessage
from vanessa.infrastructure.db.message_rows import (
    JOINED_MESSAGE_SQL,
    JOINED_MESSAGE_WITH_REPLY_SQL,
    row_to_stored,
)
from vanessa.infrastructure.db.models import Message


async def get_recent(self, limit: int = 50) -> list[StoredMessage]:
    result = await self._session.execute(
        text(
            JOINED_MESSAGE_WITH_REPLY_SQL
            + """
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT :limit
                """
        ),
        {"limit": limit},
    )
    rows = list(reversed(result.mappings().all()))
    return [row_to_stored(row) for row in rows]


async def get_newer_than(
    self,
    after_message_id: int,
    limit: int = 200,
) -> list[StoredMessage]:
    """User messages with id > after_message_id, ascending (sweep cursor)."""
    result = await self._session.execute(
        text(
            JOINED_MESSAGE_SQL
            + """
                WHERE m.role = 'user' AND m.id > :after_message_id
                ORDER BY m.id ASC
                LIMIT :limit
                """
        ),
        {"after_message_id": after_message_id, "limit": limit},
    )
    return [row_to_stored(row) for row in result.mappings().all()]


async def get_messages_since(
    self,
    days: int,
    limit: int = 5000,
) -> list[StoredMessage]:
    """All messages (user + assistant) from the last ``days``, ascending.

    Used by the deterministic metrics calculator (presence, activity,
    reactivity, counters) which needs interleaved messages across senders.
    """
    since = datetime.now(UTC) - timedelta(days=days)
    result = await self._session.execute(
        text(
            JOINED_MESSAGE_SQL
            + """
                WHERE m.created_at >= :since
                ORDER BY m.created_at ASC, m.id ASC
                LIMIT :limit
                """
        ),
        {"since": since, "limit": limit},
    )
    return [row_to_stored(row) for row in result.mappings().all()]


async def count_newer_than(self, after_message_id: int) -> int:
    result = await self._session.execute(
        select(func.count(Message.id)).where(
            Message.role == RAG_SOURCE_ROLE,
            Message.id > after_message_id,
        )
    )
    return int(result.scalar_one())


async def fulltext_search(
    self,
    query: str,
    limit: int = 30,
) -> list[StoredMessage]:
    result = await self._session.execute(
        text(
            """
                SELECT id, sender_telegram_id, telegram_message_id, role, content,
                       qdrant_point_id, created_at, attachments, photo_caption
                FROM messages
                WHERE role = 'user'
                  AND search_vector @@ plainto_tsquery('russian', :query)
                ORDER BY ts_rank(
                    search_vector,
                    plainto_tsquery('russian', :query)
                ) DESC
                LIMIT :limit
                """
        ),
        {"query": query, "limit": limit},
    )
    return [row_to_stored(row) for row in result.mappings().all()]


async def search_photo_messages(
    self,
    query: str,
    limit: int = 30,
) -> list[StoredMessage]:
    """FTS over messages that carry a photo (attachments non-empty).

    Used by the "RAG по смыслу" photo-album gathering: finds photo messages
    whose content/caption matches the meaning of the current turn. Runs
    inside a SAVEPOINT: the compose stage treats this as an optional,
    fail-open read, and a swallowed failure must not poison the shared
    request transaction (see ``_savepoint``).
    """
    async with self._savepoint():
        result = await self._session.execute(
            text(
                JOINED_MESSAGE_SQL
                + """
                    WHERE m.role = 'user'
                      AND m.attachments IS NOT NULL
                      AND jsonb_typeof(m.attachments) = 'array'
                      AND jsonb_array_length(m.attachments) > 0
                      AND m.search_vector @@ plainto_tsquery('russian', :query)
                    ORDER BY ts_rank(
                        m.search_vector,
                        plainto_tsquery('russian', :query)
                    ) DESC, m.id DESC
                    LIMIT :limit
                    """
            ),
            {"query": query, "limit": limit},
        )
        return [row_to_stored(row) for row in result.mappings().all()]
