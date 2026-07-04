from datetime import datetime, timezone

from app.core.messages import ContextMessage, StoredMessage
from app.db.mappers import (
    message_to_context,
    message_to_stored,
    messages_stored_to_context,
    messages_to_context,
)
from app.db.models import Message


def test_message_to_stored_maps_fields():
    created = datetime(2024, 1, 1, tzinfo=timezone.utc)
    message = Message(
        id=1,
        role="user",
        content="hello",
        sender_telegram_id=42,
        telegram_message_id=99,
        qdrant_point_id="pt-1",
        created_at=created,
    )
    stored = message_to_stored(message)
    assert stored.id == 1
    assert stored.sender_telegram_id == 42
    assert stored.created_at == created


def test_message_to_context():
    message = Message(id=2, role="user", content="ctx")
    context = message_to_context(message)
    assert isinstance(context, ContextMessage)
    assert context.id == 2
    assert context.content == "ctx"


def test_messages_to_context_batch():
    messages = [
        Message(id=1, role="user", content="a"),
        Message(id=2, role="user", content="b"),
    ]
    contexts = messages_to_context(messages)
    assert [item.id for item in contexts] == [1, 2]


def test_messages_stored_to_context_batch():
    stored = [
        StoredMessage(id=3, role="user", content="x"),
        StoredMessage(id=4, role="user", content="y"),
    ]
    contexts = messages_stored_to_context(stored)
    assert len(contexts) == 2
    assert contexts[1].content == "y"
