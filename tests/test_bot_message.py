from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ChatType

from app.bot.messages import IncomingMessage
from app.bot.services.api_client import HttpChatApiClient
from app.decision.models import DecisionAction


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


def test_is_text_false_for_empty_message():
    incoming = IncomingMessage.from_telegram(make_telegram_message(text="  "))

    assert incoming.is_text is False


@pytest.mark.asyncio
async def test_api_client_sends_request_id_header():
    incoming = IncomingMessage.from_telegram(make_telegram_message())
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "action": "ignore",
        "reason": "ignore",
        "reply": None,
        "relevance_score": 0.2,
    }
    mock_client.post = AsyncMock(return_value=mock_response)

    api = HttpChatApiClient(client=mock_client)
    await api.process(incoming)

    headers = mock_client.post.await_args.kwargs["headers"]
    assert headers["X-Request-ID"] == "-100123:99"


@pytest.mark.asyncio
async def test_api_client_parses_ignore_response():
    incoming = IncomingMessage.from_telegram(make_telegram_message())
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "action": "ignore",
        "reason": "ignore",
        "reply": None,
        "relevance_score": 0.2,
    }
    mock_client.post = AsyncMock(return_value=mock_response)

    api = HttpChatApiClient(client=mock_client)
    result = await api.process(incoming)

    assert result.action == DecisionAction.IGNORE
    assert result.reply is None
    assert result.relevance_score == 0.2


@pytest.mark.asyncio
async def test_api_client_parses_reply_response():
    incoming = IncomingMessage.from_telegram(make_telegram_message())
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "action": "reply",
        "reason": "intent",
        "reply": "Привет!",
        "relevance_score": 0.1,
    }
    mock_client.post = AsyncMock(return_value=mock_response)

    api = HttpChatApiClient(client=mock_client)
    result = await api.process(incoming)

    assert result.action == DecisionAction.REPLY
    assert result.reply == "Привет!"
