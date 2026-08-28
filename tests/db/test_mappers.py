from datetime import datetime, timezone

from app.core.messages import ContextMessage, StoredMessage, stored_to_context
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
        reply_to_message_id=555,
        reply_to_text="Личь не делает карты",
        reply_to_sender_telegram_id=99,
        reply_to_sender_name="Личь",
    )
    stored = message_to_stored(message)
    assert stored.id == 1
    assert stored.sender_telegram_id == 42
    assert stored.created_at == created
    assert stored.reply_to_message_id == 555
    assert stored.reply_to_text == "Личь не делает карты"
    assert stored.reply_to_sender_telegram_id == 99
    assert stored.reply_to_sender_name == "Личь"


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


def test_message_to_stored_maps_attachments():
    message = Message(
        id=10,
        role="user",
        content="фото",
        attachments=[
            {
                "data_url": "data:image/jpeg;base64,AAAA",
                "mime_type": "image/jpeg",
                "telegram_file_id": "f1",
            }
        ],
    )
    stored = message_to_stored(message)
    assert stored.attachments == [
        {
            "data_url": "data:image/jpeg;base64,AAAA",
            "mime_type": "image/jpeg",
            "telegram_file_id": "f1",
        }
    ]
    # stored_to_context converts the raw dicts into ImageAttachment objects so
    # the session/vision pipeline can consume them.
    context = stored_to_context(stored)
    assert len(context.attachments) == 1
    assert context.attachments[0].data_url == "data:image/jpeg;base64,AAAA"
    assert context.attachments[0].mime_type == "image/jpeg"
    assert context.attachments[0].telegram_file_id == "f1"


def test_stored_to_context_without_attachments_is_empty():
    stored = StoredMessage(id=1, role="user", content="x")
    context = stored_to_context(stored)
    assert context.attachments == ()


def test_stored_to_context_maps_photo_caption():
    stored = StoredMessage(
        id=2,
        role="user",
        content="[фото]",
        attachments=[
            {
                "data_url": "data:image/jpeg;base64,AAAA",
                "mime_type": "image/jpeg",
                "telegram_file_id": "f1",
            }
        ],
        photo_caption="кот на диване",
    )
    context = stored_to_context(stored)
    assert context.photo_caption == "кот на диване"
    assert context.attachments[0].telegram_file_id == "f1"


def test_message_to_stored_maps_photo_caption():
    message = Message(
        id=3,
        role="user",
        content="[фото]",
        attachments=[
            {
                "data_url": "data:image/jpeg;base64,AAAA",
                "mime_type": "image/jpeg",
                "telegram_file_id": "f1",
            }
        ],
        photo_caption="кот на диване",
    )
    stored = message_to_stored(message)
    assert stored.photo_caption == "кот на диване"
