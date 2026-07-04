from dataclasses import dataclass
from datetime import datetime

RAG_SOURCE_ROLE = "user"


@dataclass(frozen=True, slots=True)
class ContextMessage:
    id: int
    role: str
    content: str
    sender_telegram_id: int | None = None
    sender_name: str | None = None
    created_at: datetime | None = None
    is_anchor: bool = False


@dataclass(frozen=True, slots=True)
class ContextBlock:
    anchor_id: int
    messages: tuple[ContextMessage, ...]


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: int
    role: str
    content: str
    sender_telegram_id: int | None = None
    qdrant_point_id: str | None = None
    telegram_message_id: int | None = None
    sender_name: str | None = None
    created_at: datetime | None = None


def stored_to_context(
    message: StoredMessage,
    *,
    is_anchor: bool = False,
) -> ContextMessage:
    return ContextMessage(
        id=message.id,
        role=message.role,
        content=message.content,
        sender_telegram_id=message.sender_telegram_id,
        sender_name=message.sender_name,
        created_at=message.created_at,
        is_anchor=is_anchor,
    )


def stored_block_to_context(
    anchor_id: int,
    messages: list[StoredMessage],
) -> ContextBlock | None:
    user_messages = [message for message in messages if message.role == RAG_SOURCE_ROLE]
    if not user_messages:
        return None
    anchor_id = next(
        (message.id for message in user_messages if message.id == anchor_id),
        user_messages[-1].id,
    )
    return ContextBlock(
        anchor_id=anchor_id,
        messages=tuple(
            stored_to_context(message, is_anchor=message.id == anchor_id)
            for message in user_messages
        ),
    )


def context_block_message_count(blocks: list[ContextBlock]) -> int:
    return sum(len(block.messages) for block in blocks)
