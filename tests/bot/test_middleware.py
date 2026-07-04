from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, Update, User

from app.bot.middleware.logging import (
    BotLoggingMiddleware,
    _event_label,
    _resolve_request_id,
)


def _telegram_message() -> Message:
    return Message(
        message_id=99,
        date=1,
        chat=Chat(id=-100123, type="group"),
        from_user=User(id=42, is_bot=False, first_name="Test"),
        text="Привет",
    )


def test_resolve_request_id_from_message():
    message = _telegram_message()
    assert _resolve_request_id(message) == "-100123:99"


def test_resolve_request_id_from_update():
    message = _telegram_message()
    update = Update(update_id=1, message=message)
    assert _resolve_request_id(update) == "-100123:99"


def test_event_label_for_message():
    message = _telegram_message()
    assert _event_label(message) == message.content_type


@pytest.mark.asyncio
async def test_logging_middleware_invokes_handler():
    middleware = BotLoggingMiddleware()
    message = _telegram_message()
    handler = AsyncMock(return_value="ok")
    result = await middleware(handler, message, {})
    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_logging_middleware_reraises_errors():
    middleware = BotLoggingMiddleware()
    message = _telegram_message()
    handler = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        await middleware(handler, message, {})
