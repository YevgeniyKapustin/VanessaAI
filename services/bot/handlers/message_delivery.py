import logging
from collections.abc import Awaitable, Callable

from aiogram.types import Message as TelegramMessage

from services.bot.container import BotServices
from services.bot.handlers.message_process import _process_incoming, _should_ignore
from services.bot.handlers.message_send import (
    _send_photo,
    _send_reply,
    _send_reply_messages,
)
from services.bot.handlers.message_typing import _ping_typing, _typing_on_signal
from services.bot.messages import IncomingMessage
from services.bot.messages.response import ChatProcessResult
from services.bot.stickers.heuristics import is_sticker_request

logger = logging.getLogger("services.bot.handlers.messages")

_PREVIEW_LEN = 80


def _preview(text: str) -> str:
    normalized = text.replace("\n", " ").strip()
    if len(normalized) <= _PREVIEW_LEN:
        return normalized
    return f"{normalized[:_PREVIEW_LEN]}..."


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


async def _deliver_tagged_reply(
    telegram_message: TelegramMessage,
    incoming: IncomingMessage,
    services: BotServices,
    result: ChatProcessResult,
) -> None:
    await _ping_typing(
        telegram_message.bot, incoming.telegram_chat_id, "pre_reply"
    )
    blocks = result.messages or ([result.reply] if result.reply else [])
    if services.max_messages > 0 and len(blocks) > services.max_messages:
        logger.warning(
            "reply_blocks_capped chat_id=%s blocks=%s cap=%s",
            incoming.telegram_chat_id,
            len(blocks),
            services.max_messages,
        )
        blocks = blocks[: services.max_messages]
    await _send_reply_messages(
        telegram_message,
        blocks,
        delay=services.message_delay_seconds,
    )
    logger.info(
        "reply_sent chat_id=%s reply_len=%s messages=%s",
        incoming.telegram_chat_id,
        len(result.reply or ""),
        len(blocks),
    )
    if result.photo_file_id:
        sent = await _send_photo(
            telegram_message,
            result.photo_file_id,
            data_url=result.photo_data_url,
        )
        logger.info(
            "photo_sent chat_id=%s file_id=%s sent=%s",
            incoming.telegram_chat_id,
            result.photo_file_id,
            sent,
        )
    if services.stickers is not None:
        services.stickers.register_reply(incoming.telegram_chat_id)
        await services.stickers.send_if_any(
            telegram_message,
            sticker_tag=result.sticker_tag,
            reply_text=result.reply,
            force=is_sticker_request(incoming.text),
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
