from datetime import datetime
from typing import Protocol

from vanessa.core.messages import StoredMessage


class UnitOfWorkProtocol(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class MessageRepositoryProtocol(Protocol):
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
        channel: str = "telegram",
        sender_display_name: str | None = None,
    ) -> StoredMessage: ...

    async def fulltext_search(
        self,
        query: str,
        limit: int = 30,
        *,
        channel: str = "telegram",
    ) -> list[StoredMessage]: ...

    async def get_by_ids(self, message_ids: list[int]) -> list[StoredMessage]: ...

    async def get_conversation_window_blocks(
        self,
        anchor_ids: list[int],
        before: int = 10,
        after: int = 10,
        max_total: int = 80,
    ) -> list[tuple[int, list[StoredMessage]]]: ...

    async def get_newer_than(
        self,
        after_message_id: int,
        limit: int = 200,
    ) -> list[StoredMessage]: ...

    async def get_messages_since(
        self,
        days: int,
        limit: int = 5000,
    ) -> list[StoredMessage]: ...

    async def get_recent(
        self,
        limit: int = 50,
        *,
        channel: str = "telegram",
    ) -> list[StoredMessage]: ...

    async def get_existing_telegram_message_ids(
        self,
        telegram_message_ids: list[int],
    ) -> set[int]: ...

    async def update_photo_caption(
        self,
        message_id: int,
        caption: str,
    ) -> None: ...

    async def search_photo_messages(
        self,
        query: str,
        limit: int = 30,
        *,
        channel: str = "telegram",
    ) -> list[StoredMessage]: ...


class ChatUserProtocol(Protocol):
    nickname: str | None
    first_name: str | None
    username: str | None


class UserRepositoryProtocol(Protocol):
    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> ChatUserProtocol: ...
