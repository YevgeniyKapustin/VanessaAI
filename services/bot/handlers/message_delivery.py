import logging
from collections.abc import Awaitable, Callable

from aiogram.types import Message as TelegramMessage

from services.bot.container import BotServices
from services.bot.handlers.message_preview import _preview
from services.bot.handlers.message_process import _process_incoming, _should_ignore
from services.bot.handlers.message_send import _send_reply
from services.bot.handlers.message_tagged import _deliver_tagged_reply
from services.bot.handlers.message_typing import _ping_typing, _typing_on_signal
from services.bot.messages import IncomingMessage
from services.bot.messages.response import ChatProcessResult

logger = logging.getLogger("services.bot.handlers.messages")


async def _reject_if_no_access(
    services: BotServices,
    telegram_message: TelegramMessage,
    incoming: IncomingMessage,
) -> bool:
    error = await services.access_guard.ensure_access(incoming)
    if error:
        logger.info(
            "access_denied chat_id=%s sender_id=%s chat_type=%s",
            incoming.telegram_chat_id,
            incoming.sender_telegram_id,
            incoming.chat_type,
        )
        await telegram_message.answer(error)
        return True
    return False


async def _deliver_sticker_only(
    telegram_message: TelegramMessage,
    incoming: IncomingMessage,
    services: BotServices,
    result: ChatProcessResult,
) -> None:
    services.stickers.register_reply(incoming.telegram_chat_id)
    await _ping_typing(
        telegram_message.bot, incoming.telegram_chat_id, "pre_reply"
    )
    sent = await services.stickers.send_if_any(
        telegram_message,
        sticker_tag=result.sticker_tag,
        reply_text=None,
        force=True,
    )
    logger.info(
        "sticker_only chat_id=%s tag=%s sent=%s",
        incoming.telegram_chat_id,
        result.sticker_tag,
        sent,
    )
    if sent is not None:
        return
    if result.reply:
        await _send_reply(telegram_message, result.reply)
        return
    logger.warning(
        "sticker_only_failed chat_id=%s tag=%s no_text_fallback",
        incoming.telegram_chat_id,
        result.sticker_tag,
    )


async def _run_with_typing(
    telegram_message: TelegramMessage,
    incoming: IncomingMessage,
    services: BotServices,
) -> None:
    async with _typing_on_signal(
        telegram_message.bot,
        incoming.telegram_chat_id,
        interval=services.typing_interval_seconds,
    ) as start_typing:
        await _handle_text_core(
            telegram_message, incoming, services, start_typing
        )


async def _handle_text_core(
    telegram_message: TelegramMessage,
    incoming: IncomingMessage,
    services: BotServices,
    start_typing: Callable[[], Awaitable[None]],
) -> None:
    if await _reject_if_no_access(services, telegram_message, incoming):
        return

    logger.info(
        "message_received chat_id=%s sender_id=%s text=%r",
        incoming.telegram_chat_id,
        incoming.sender_telegram_id,
        _preview(incoming.text),
    )

    result = await _process_incoming(services, incoming, start_typing)
    if result is None:
        return
    if _should_ignore(result):
        logger.info(
            "message_ignored chat_id=%s reason=%s relevance=%.3f",
            incoming.telegram_chat_id,
            result.reason,
            result.relevance_score,
        )
        return
    await _deliver_reply_or_sticker(
        telegram_message, incoming, services, result
    )


async def _deliver_reply_or_sticker(
    telegram_message: TelegramMessage,
    incoming: IncomingMessage,
    services: BotServices,
    result: ChatProcessResult,
) -> None:
    if services.stickers is not None and services.stickers.is_sticker_only(
        result.sticker_tag
    ):
        await _deliver_sticker_only(
            telegram_message, incoming, services, result
        )
        return
    await _deliver_tagged_reply(telegram_message, incoming, services, result)
