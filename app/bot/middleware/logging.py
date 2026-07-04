from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from app.core.request_context import request_id_var

logger = logging.getLogger(__name__)


def _resolve_request_id(event: TelegramObject) -> str:
    if isinstance(event, Message):
        return f"{event.chat.id}:{event.message_id}"
    if isinstance(event, Update):
        message = event.message or event.edited_message
        if message is not None:
            return f"{message.chat.id}:{message.message_id}"
    return "-"


def _event_label(event: TelegramObject) -> str:
    if isinstance(event, Message):
        return event.content_type
    if isinstance(event, Update):
        return event.event_type
    return type(event).__name__


class BotLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        request_id = _resolve_request_id(event)
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        logger.info("update_received type=%s", _event_label(event))
        try:
            return await handler(event, data)
        except Exception:
            logger.exception(
                "update_failed type=%s duration_ms=%.1f",
                _event_label(event),
                (time.perf_counter() - started) * 1000,
            )
            raise
        finally:
            logger.info(
                "update_handled type=%s duration_ms=%.1f",
                _event_label(event),
                (time.perf_counter() - started) * 1000,
            )
            request_id_var.reset(token)
