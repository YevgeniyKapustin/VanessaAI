import logging

from aiogram.types import Message as TelegramMessage

from services.bot.container import BotServices
from services.bot.handlers.message_send import _send_photo, _send_reply_messages
from services.bot.handlers.message_speech import maybe_send_voice, omit_text_after_voice
from services.bot.handlers.message_typing import _ping_typing
from services.bot.messages import IncomingMessage
from services.bot.messages.response import ChatProcessResult
from services.bot.stickers.heuristics import is_sticker_request

logger = logging.getLogger("services.bot.handlers.messages")


async def _deliver_tagged_reply(
    telegram_message: TelegramMessage,
    incoming: IncomingMessage,
    services: BotServices,
    result: ChatProcessResult,
) -> None:
    await _ping_typing(
        telegram_message.bot, incoming.telegram_chat_id, "pre_reply"
    )
    voice_sent = await maybe_send_voice(telegram_message, result, services)
    skip_text = omit_text_after_voice(
        voice_sent=voice_sent, speech_send=services.speech_send
    )
    if not skip_text:
        await _send_tagged_text(telegram_message, incoming, services, result)
    await _deliver_tagged_extras(telegram_message, incoming, services, result)


async def _send_tagged_text(
    telegram_message: TelegramMessage,
    incoming: IncomingMessage,
    services: BotServices,
    result: ChatProcessResult,
) -> None:
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


async def _deliver_tagged_extras(
    telegram_message: TelegramMessage,
    incoming: IncomingMessage,
    services: BotServices,
    result: ChatProcessResult,
) -> None:
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
