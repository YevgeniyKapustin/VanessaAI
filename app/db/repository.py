from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.messages import RAG_SOURCE_ROLE, StoredMessage
from app.db.mappers import message_to_stored
from app.db.models import Message, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        nickname: str | None = None,
    ) -> User:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is not None:
            if username and not user.username:
                user.username = username
            if first_name and not user.first_name:
                user.first_name = first_name
            if last_name and not user.last_name:
                user.last_name = last_name
            if nickname and not user.nickname:
                user.nickname = nickname
            await self._session.flush()
            return user

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            nickname=nickname,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def upsert_profile(
        self,
        telegram_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        nickname: str | None = None,
        force_nickname: bool = False,
    ) -> tuple[User, str]:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                nickname=nickname,
            )
            self._session.add(user)
            await self._session.flush()
            return user, "created"

        changed = False
        if username and not user.username:
            user.username = username
            changed = True
        if first_name and not user.first_name:
            user.first_name = first_name
            changed = True
        if last_name and not user.last_name:
            user.last_name = last_name
            changed = True
        if nickname and (force_nickname or not user.nickname):
            if user.nickname != nickname:
                user.nickname = nickname
                changed = True
        if changed:
            await self._session.flush()
            return user, "updated"
        return user, "unchanged"


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

    async def get_recent(self, limit: int = 50) -> list[StoredMessage]:
        result = await self._session.execute(
            text(
                """
                SELECT m.id, m.sender_telegram_id, m.telegram_message_id,
                       m.role, m.content, m.qdrant_point_id, m.created_at,
                       m.reply_to_message_id, m.reply_to_text,
                       m.reply_to_sender_telegram_id, m.reply_to_sender_name,
                       m.attachments, m.photo_caption,
                       COALESCE(u.nickname, u.first_name, u.username) AS sender_name
                FROM messages m
                LEFT JOIN users u ON u.telegram_id = m.sender_telegram_id
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        rows = list(reversed(result.mappings().all()))
        return [self._row_to_stored(row) for row in rows]

    async def get_newer_than(
        self,
        after_message_id: int,
        limit: int = 200,
    ) -> list[StoredMessage]:
        """User messages with id > after_message_id, ascending (sweep cursor)."""
        result = await self._session.execute(
            text(
                """
                SELECT m.id, m.sender_telegram_id, m.telegram_message_id,
                       m.role, m.content, m.qdrant_point_id, m.created_at,
                       m.attachments, m.photo_caption,
                       COALESCE(u.nickname, u.first_name, u.username) AS sender_name
                FROM messages m
                LEFT JOIN users u ON u.telegram_id = m.sender_telegram_id
                WHERE m.role = 'user' AND m.id > :after_message_id
                ORDER BY m.id ASC
                LIMIT :limit
                """
            ),
            {"after_message_id": after_message_id, "limit": limit},
        )
        return [self._row_to_stored(row) for row in result.mappings().all()]

    async def get_messages_since(
        self,
        days: int,
        limit: int = 5000,
    ) -> list[StoredMessage]:
        """All messages (user + assistant) from the last ``days``, ascending.

        Used by the deterministic metrics calculator (presence, activity,
        reactivity, counters) which needs interleaved messages across senders.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            text(
                """
                SELECT m.id, m.sender_telegram_id, m.telegram_message_id,
                       m.role, m.content, m.qdrant_point_id, m.created_at,
                       m.attachments, m.photo_caption,
                       COALESCE(u.nickname, u.first_name, u.username) AS sender_name
                FROM messages m
                LEFT JOIN users u ON u.telegram_id = m.sender_telegram_id
                WHERE m.created_at >= :since
                ORDER BY m.created_at ASC, m.id ASC
                LIMIT :limit
                """
            ),
            {"since": since, "limit": limit},
        )
        return [self._row_to_stored(row) for row in result.mappings().all()]

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
        rows = result.mappings().all()
        return [
            StoredMessage(
                id=row["id"],
                sender_telegram_id=row["sender_telegram_id"],
                telegram_message_id=row["telegram_message_id"],
                role=row["role"],
                content=row["content"],
                qdrant_point_id=row["qdrant_point_id"],
                created_at=row["created_at"],
                attachments=row["attachments"],
                photo_caption=row["photo_caption"],
            )
            for row in rows
        ]

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
                    """
                    SELECT m.id, m.sender_telegram_id, m.telegram_message_id,
                           m.role, m.content, m.qdrant_point_id, m.created_at,
                           m.attachments, m.photo_caption,
                           COALESCE(u.nickname, u.first_name, u.username) AS sender_name
                    FROM messages m
                    LEFT JOIN users u ON u.telegram_id = m.sender_telegram_id
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
            return [
                self._row_to_stored(row)
                for row in result.mappings().all()
            ]

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

    @staticmethod
    def _row_to_stored(row) -> StoredMessage:
        return StoredMessage(
            id=row["id"],
            sender_telegram_id=row["sender_telegram_id"],
            telegram_message_id=row["telegram_message_id"],
            role=row["role"],
            content=row["content"],
            qdrant_point_id=row["qdrant_point_id"],
            created_at=row["created_at"],
            sender_name=row.get("sender_name"),
            reply_to_message_id=row.get("reply_to_message_id"),
            reply_to_text=row.get("reply_to_text"),
            reply_to_sender_telegram_id=row.get("reply_to_sender_telegram_id"),
            reply_to_sender_name=row.get("reply_to_sender_name"),
            attachments=row.get("attachments"),
            photo_caption=row.get("photo_caption"),
        )

    async def _window_for_anchor(
        self,
        anchor_id: int,
        before: int,
        after: int,
    ) -> list[StoredMessage]:
        anchor = await self.get_by_id(anchor_id)
        if anchor is None or anchor.created_at is None or anchor.role != RAG_SOURCE_ROLE:
            return []

        before_rows: list[StoredMessage] = []
        if before > 0:
            result = await self._session.execute(
                text(
                    """
                    SELECT m.id, m.sender_telegram_id, m.telegram_message_id,
                           m.role, m.content, m.qdrant_point_id, m.created_at,
                           m.attachments, m.photo_caption,
                           COALESCE(u.nickname, u.first_name, u.username) AS sender_name
                    FROM messages m
                    LEFT JOIN users u ON u.telegram_id = m.sender_telegram_id
                    WHERE m.role = 'user'
                      AND (m.created_at, m.id) < (:created_at, :anchor_id)
                    ORDER BY m.created_at DESC, m.id DESC
                    LIMIT :limit
                    """
                ),
                {
                    "created_at": anchor.created_at,
                    "anchor_id": anchor_id,
                    "limit": before,
                },
            )
            before_rows = [
                self._row_to_stored(row)
                for row in reversed(result.mappings().all())
            ]

        anchor_row = await self._session.execute(
            text(
                """
                SELECT m.id, m.sender_telegram_id, m.telegram_message_id,
                       m.role, m.content, m.qdrant_point_id, m.created_at,
                       m.attachments, m.photo_caption,
                       COALESCE(u.nickname, u.first_name, u.username) AS sender_name
                FROM messages m
                LEFT JOIN users u ON u.telegram_id = m.sender_telegram_id
                WHERE m.id = :anchor_id
                """
            ),
            {"anchor_id": anchor_id},
        )
        anchor_message = anchor_row.mappings().first()
        if anchor_message is None:
            return before_rows
        center = [self._row_to_stored(anchor_message)]

        after_rows: list[StoredMessage] = []
        if after > 0:
            result = await self._session.execute(
                text(
                    """
                    SELECT m.id, m.sender_telegram_id, m.telegram_message_id,
                           m.role, m.content, m.qdrant_point_id, m.created_at,
                           m.attachments, m.photo_caption,
                           COALESCE(u.nickname, u.first_name, u.username) AS sender_name
                    FROM messages m
                    LEFT JOIN users u ON u.telegram_id = m.sender_telegram_id
                    WHERE m.role = 'user'
                      AND (m.created_at, m.id) > (:created_at, :anchor_id)
                    ORDER BY m.created_at ASC, m.id ASC
                    LIMIT :limit
                    """
                ),
                {
                    "created_at": anchor.created_at,
                    "anchor_id": anchor_id,
                    "limit": after,
                },
            )
            after_rows = [self._row_to_stored(row) for row in result.mappings().all()]

        return before_rows + center + after_rows

    async def get_conversation_window_blocks(
        self,
        anchor_ids: list[int],
        before: int = 10,
        after: int = 10,
        max_total: int = 80,
    ) -> list[tuple[int, list[StoredMessage]]]:
        if not anchor_ids:
            return []
        if before <= 0 and after <= 0:
            messages = await self.get_by_ids(anchor_ids)
            return [
                (message.id, [message])
                for message in messages
                if message.role == RAG_SOURCE_ROLE
            ]

        blocks: list[tuple[int, list[StoredMessage]]] = []
        total = 0
        for anchor_id in anchor_ids:
            if total >= max_total:
                break
            window = await self._window_for_anchor(anchor_id, before, after)
            if not window:
                continue
            remaining = max_total - total
            if len(window) > remaining:
                window = window[:remaining]
            blocks.append((anchor_id, window))
            total += len(window)
        return blocks

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
