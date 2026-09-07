import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message as TelegramMessage

from services.bot.container import BotServices
from services.bot.handlers.message_delivery import (
    _reject_if_no_access,
    _run_with_typing,
)
from services.bot.handlers.message_photos import (
    _pick_photo_size,
    _register_photo_handler,
)
from services.bot.handlers.message_preview import _PREVIEW_LEN, _preview
from services.bot.handlers.message_send import (
    _send_photo,
    _send_reply,
    _send_reply_messages,
)
from services.bot.handlers.message_typing import (
    _typing_loop,
    _typing_on_signal,
)
from services.bot.messages import IncomingMessage

logger = logging.getLogger(__name__)

__all__ = [
    "_PREVIEW_LEN",
    "_pick_photo_size",
    "_preview",
    "_send_photo",
    "_send_reply",
    "_send_reply_messages",
    "_typing_loop",
    "_typing_on_signal",
    "create_messages_router",
]


async def _cmd_start(
    services: BotServices, telegram_message: TelegramMessage
) -> None:
    incoming = IncomingMessage.from_telegram(telegram_message)
    if await _reject_if_no_access(services, telegram_message, incoming):
        return
    logger.info(
        "command_start chat_id=%s sender_id=%s",
        incoming.telegram_chat_id,
        incoming.sender_telegram_id,
    )
    await telegram_message.answer(services.texts.welcome.strip())
    await _send_greeting_sticker(services, telegram_message, incoming)


async def _send_greeting_sticker(
    services: BotServices,
    telegram_message: TelegramMessage,
    incoming: IncomingMessage,
) -> None:
    if services.stickers is None:
        return
    services.stickers.register_reply(incoming.telegram_chat_id)
    await services.stickers.send_if_any(
        telegram_message,
        sticker_tag="greeting",
    )


def create_messages_router(services: BotServices) -> Router:
    router = Router()

    async def cmd_start(telegram_message: TelegramMessage) -> None:
        await _cmd_start(services, telegram_message)

    async def handle_text(telegram_message: TelegramMessage) -> None:
        incoming = IncomingMessage.from_telegram(telegram_message)
        await _run_with_typing(telegram_message, incoming, services)

    router.message.register(cmd_start, CommandStart())
    router.message.register(handle_text, F.text)
    _register_photo_handler(router, services)
    return router
