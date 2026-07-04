from app.core.messages import ContextMessage, StoredMessage, stored_to_context
from app.db.models import Message


def message_to_stored(message: Message) -> StoredMessage:
    return StoredMessage(
        id=message.id,
        role=message.role,
        content=message.content,
        sender_telegram_id=message.sender_telegram_id,
        qdrant_point_id=message.qdrant_point_id,
        telegram_message_id=message.telegram_message_id,
        created_at=message.created_at,
    )


def message_to_context(message: Message) -> ContextMessage:
    return stored_to_context(message_to_stored(message))


def messages_to_context(messages: list[Message]) -> list[ContextMessage]:
    return [message_to_context(message) for message in messages]


def messages_stored_to_context(messages: list[StoredMessage]) -> list[ContextMessage]:
    return [stored_to_context(message) for message in messages]
