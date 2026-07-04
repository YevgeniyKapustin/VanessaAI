from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest

from app.bot.container import BotServices, create_bot_services
from app.bot.handlers.messages import _preview, _send_reply, create_messages_router
from app.bot.messages.response import ChatProcessResult
from app.config.content import get_content
from tests.bot.test_bot_message import make_telegram_message


@pytest.mark.asyncio
async def test_preview_truncates_long_text():
    text = "a" * 120
    assert _preview(text).endswith("...")
    assert len(_preview(text)) <= 83


def test_create_bot_services_wires_dependencies():
    services = create_bot_services()
    assert services.chat_client is not None
    assert services.access_guard is not None
    assert services.texts.welcome == get_content().bot.welcome


@pytest.mark.asyncio
async def test_send_reply_falls_back_on_bad_html():
    message = make_telegram_message()
    message.reply = AsyncMock(
        side_effect=[TelegramBadRequest(MagicMock(), "bad"), None]
    )
    await _send_reply(message, "plain text")
    assert message.reply.await_count == 2
    second_call = message.reply.await_args_list[1]
    assert second_call.args[0] == "plain text"


@pytest.mark.asyncio
async def test_send_reply_uses_html_parse_mode():
    message = make_telegram_message()
    message.reply = AsyncMock()
    await _send_reply(message, "code `x`")
    message.reply.assert_awaited_once()
    assert message.reply.await_args.kwargs["parse_mode"] == ParseMode.HTML


def _services(
    *,
    access_error: str | None = None,
    api_result: ChatProcessResult | None = None,
    api_error: Exception | None = None,
) -> BotServices:
    chat_client = AsyncMock()
    if api_error is not None:
        chat_client.process = AsyncMock(side_effect=api_error)
    else:
        chat_client.process = AsyncMock(
            return_value=api_result
            or ChatProcessResult(
                action="ignore",
                reason="ignore",
                reply=None,
                relevance_score=0.0,
            )
        )
    access_guard = AsyncMock()
    access_guard.ensure_access = AsyncMock(return_value=access_error)
    return BotServices(
        chat_client=chat_client,
        access_guard=access_guard,
        texts=get_content().bot,
    )


async def _call_text_handler(services: BotServices, message: MagicMock) -> None:
    router = create_messages_router(services)
    handler = router.message.handlers[-1].callback
    await handler(message)


async def _call_start_handler(services: BotServices, message: MagicMock) -> None:
    router = create_messages_router(services)
    handler = router.message.handlers[0].callback
    await handler(message)


@pytest.mark.asyncio
async def test_handle_text_ignores_when_access_denied():
    message = make_telegram_message()
    message.answer = AsyncMock()
    services = _services(access_error="no access")
    await _call_text_handler(services, message)
    message.answer.assert_awaited_once_with("no access")
    services.chat_client.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_text_reports_api_error():
    message = make_telegram_message()
    message.reply = AsyncMock()
    services = _services(api_error=httpx.ConnectError("down"))
    await _call_text_handler(services, message)
    message.reply.assert_awaited_once_with(services.texts.error_api)


@pytest.mark.asyncio
async def test_handle_text_sends_reply():
    message = make_telegram_message(text="Vanessa?")
    message.reply = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Да?",
            relevance_score=0.9,
        )
    )
    await _call_text_handler(services, message)
    message.bot.send_chat_action.assert_awaited_once()
    message.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_text_ignores_non_reply():
    message = make_telegram_message(text="просто болтовня")
    message.answer = AsyncMock()
    message.reply = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="ignore",
            reason="noise",
            reply=None,
            relevance_score=0.1,
        )
    )
    await _call_text_handler(services, message)
    message.answer.assert_not_awaited()
    message.reply.assert_not_awaited()
    message.bot.send_chat_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_start_sends_welcome():
    message = make_telegram_message(text="/start")
    message.answer = AsyncMock()
    services = _services()
    await _call_start_handler(services, message)
    message.answer.assert_awaited_once()
    assert services.texts.welcome.strip() in message.answer.await_args.args[0]


def test_create_router_includes_messages():
    from app.bot.handlers import create_router

    router = create_router(create_bot_services())
    assert router.sub_routers
