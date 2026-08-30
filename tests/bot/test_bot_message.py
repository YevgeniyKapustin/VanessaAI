from unittest.mock import AsyncMock, MagicMock

from aiogram.enums import ChatType

from services.bot.messages import IncomingMessage


def make_telegram_message(
    text: str = "Привет",
    chat_type: ChatType = ChatType.GROUP,
) -> MagicMock:
    message = MagicMock()
    message.chat.id = -100123
    message.chat.type = chat_type
    message.chat.title = "Test chat"
    message.message_id = 99
    message.text = text
    message.from_user.id = 42
    message.from_user.username = "tester"
    message.from_user.first_name = "Test"
    message.from_user.last_name = "User"
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    message.media_group_id = None
    return message


def test_from_telegram_maps_fields():
    incoming = IncomingMessage.from_telegram(make_telegram_message())

    assert incoming.telegram_chat_id == -100123
    assert incoming.text == "Привет"
    assert incoming.sender_telegram_id == 42
    assert incoming.chat_type == ChatType.GROUP.value
    assert incoming.chat_title == "Test chat"


def test_from_telegram_accepts_string_chat_type():
    message = make_telegram_message()
    message.chat.type = ChatType.GROUP.value

    incoming = IncomingMessage.from_telegram(message)

    assert incoming.chat_type == ChatType.GROUP.value


def test_to_api_payload_contains_chat_context():
    incoming = IncomingMessage.from_telegram(make_telegram_message())

    payload = incoming.to_api_payload()

    assert payload["telegram_chat_id"] == -100123
    assert payload["message"] == "Привет"
    assert payload["sender_telegram_id"] == 42


def test_to_api_payload_contains_reply_context():
    message = make_telegram_message()
    reply = MagicMock()
    reply.message_id = 555
    reply.text = "Личь не делает карты"
    reply.caption = None
    reply.sticker = None
    reply.from_user.id = 99
    reply.from_user.username = "lich"
    reply.from_user.first_name = None
    reply.from_user.last_name = None
    message.reply_to_message = reply

    incoming = IncomingMessage.from_telegram(message)
    payload = incoming.to_api_payload()

    assert payload["reply_to_message_id"] == 555
    assert payload["reply_to_text"] == "Личь не делает карты"
    assert payload["reply_to_sender_name"] == "lich"
    assert payload["reply_to_other_user"] is True


def test_is_text_false_for_empty_message():
    incoming = IncomingMessage.from_telegram(make_telegram_message(text="  "))

    assert incoming.is_text is False
