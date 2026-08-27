import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ChatType

from app.bot.messages import IncomingMessage
from app.bot.services.api_client import HttpChatApiClient
from app.decision.models import DecisionAction


def _stream_ctx(
    payload: dict,
    *,
    with_started: bool = True,
    content_type: str = "text/event-stream",
):
    """Mock async context returned by ``client.stream`` for an SSE response."""
    mock_response = MagicMock()
    mock_response.headers = {"content-type": content_type}
    lines = []
    if with_started:
        lines += ["event: started", "data: {}", ""]
    lines += [
        "event: result",
        "data: " + json.dumps(payload, ensure_ascii=False),
        "",
    ]

    async def _iter_lines():
        for line in lines:
            yield line

    mock_response.aiter_lines = MagicMock(side_effect=_iter_lines)
    if content_type != "text/event-stream":
        mock_response.json.return_value = payload
    ctx = AsyncMock()
    ctx.__aenter__.return_value = mock_response
    return ctx


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


@pytest.mark.asyncio
async def test_api_client_sends_request_id_header():
    incoming = IncomingMessage.from_telegram(make_telegram_message())
    mock_client = MagicMock()
    mock_client.stream = MagicMock(
        return_value=_stream_ctx(
            {"action": "ignore", "reason": "ignore", "reply": None},
            with_started=False,
        )
    )

    api = HttpChatApiClient(client=mock_client)
    await api.process(incoming)

    headers = mock_client.stream.call_args.kwargs["headers"]
    assert headers["X-Request-ID"] == "-100123:99"


@pytest.mark.asyncio
async def test_api_client_parses_ignore_response():
    incoming = IncomingMessage.from_telegram(make_telegram_message())
    mock_client = MagicMock()
    mock_client.stream = MagicMock(
        return_value=_stream_ctx(
            {
                "action": "ignore",
                "reason": "ignore",
                "reply": None,
                "relevance_score": 0.2,
            },
            with_started=False,
        )
    )

    api = HttpChatApiClient(client=mock_client)
    result = await api.process(incoming)

    assert result.action == DecisionAction.IGNORE
    assert result.reply is None
    assert result.relevance_score == 0.2


@pytest.mark.asyncio
async def test_api_client_parses_reply_response():
    incoming = IncomingMessage.from_telegram(make_telegram_message())
    mock_client = MagicMock()
    mock_client.stream = MagicMock(
        return_value=_stream_ctx(
            {
                "action": "reply",
                "reason": "intent",
                "reply": "Привет!",
                "relevance_score": 0.1,
            },
            with_started=True,
        )
    )

    api = HttpChatApiClient(client=mock_client)
    result = await api.process(incoming)

    assert result.action == DecisionAction.REPLY
    assert result.reply == "Привет!"


@pytest.mark.asyncio
async def test_api_client_fires_on_started_when_gate_passes():
    incoming = IncomingMessage.from_telegram(make_telegram_message())
    mock_client = MagicMock()
    mock_client.stream = MagicMock(
        return_value=_stream_ctx(
            {
                "action": "reply",
                "reason": "intent",
                "reply": "Да?",
                "relevance_score": 0.9,
            },
            with_started=True,
        )
    )
    on_started = AsyncMock()

    api = HttpChatApiClient(client=mock_client)
    result = await api.process(incoming, on_started=on_started)

    on_started.assert_awaited_once()
    assert result.action == DecisionAction.REPLY


@pytest.mark.asyncio
async def test_api_client_skips_on_started_when_gate_ignores():
    incoming = IncomingMessage.from_telegram(make_telegram_message())
    mock_client = MagicMock()
    mock_client.stream = MagicMock(
        return_value=_stream_ctx(
            {
                "action": "ignore",
                "reason": "noise",
                "reply": None,
                "relevance_score": 0.1,
            },
            with_started=False,
        )
    )
    on_started = AsyncMock()

    api = HttpChatApiClient(client=mock_client)
    result = await api.process(incoming, on_started=on_started)

    on_started.assert_not_awaited()
    assert result.action == DecisionAction.IGNORE


@pytest.mark.asyncio
async def test_api_client_falls_back_to_plain_json():
    incoming = IncomingMessage.from_telegram(make_telegram_message())
    mock_client = MagicMock()
    mock_client.stream = MagicMock(
        return_value=_stream_ctx(
            {
                "action": "reply",
                "reason": "intent",
                "reply": "legacy",
                "relevance_score": 0.5,
            },
            content_type="application/json",
        )
    )

    api = HttpChatApiClient(client=mock_client)
    result = await api.process(incoming)

    assert result.action == DecisionAction.REPLY
    assert result.reply == "legacy"


def test_api_client_timeout_config_from_settings(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_client_read_timeout", 45.0)
    monkeypatch.setattr(settings, "api_client_connect_timeout", 5.0)

    api = HttpChatApiClient()

    assert api._timeout == 45.0
    assert api._connect_timeout == 5.0
    assert api._timeout_config.read == 45.0
    assert api._timeout_config.write == 45.0
    assert api._timeout_config.connect == 5.0
    assert api._timeout_config.pool == 5.0
