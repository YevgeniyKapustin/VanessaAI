"""Post an ``OutboundMessage`` that carries a document (a generated file).

The text is the caption when it fits Telegram's caption limit. A longer
text goes first as a normal message, then the file without a caption.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, ReplyParameters

from services.bot.outbound.send import post_outbound
from services.bot.telegram_format import markdown_to_telegram_html
from vanessa.contracts import OutboundDocument, OutboundMessage
from vanessa.infrastructure.observability.metrics import record_telegram

logger = logging.getLogger(__name__)

# Telegram caption limit (characters after entity parsing).
CAPTION_MAX_CHARS = 1024


async def post_document(bot: Bot, message: OutboundMessage) -> bool:
    """Send the file (with the text). True when Telegram took the file.

    If the file fails, the text still goes out as a normal message.
    """
    document = message.document
    if document is None:
        return await post_outbound(bot, message)
    if len(message.text) > CAPTION_MAX_CHARS:
        await post_outbound(bot, message)
        return await _send_and_record(bot, message, document, None)
    if await _send_and_record(bot, message, document, message.text):
        return True
    await post_outbound(bot, message)
    return False


async def _send_and_record(
    bot: Bot,
    message: OutboundMessage,
    document: OutboundDocument,
    caption: str | None,
) -> bool:
    sent = await _send_document(bot, message, document, caption)
    record_telegram("send_document", "success" if sent else "error")
    return sent


def _caption_attempts(caption: str | None) -> list[tuple[str | None, str | None]]:
    """HTML caption first; plain caption on ``TelegramBadRequest``."""
    if caption is None:
        return [(None, None)]
    return [(markdown_to_telegram_html(caption), ParseMode.HTML), (caption, None)]


async def _send_document(
    bot: Bot,
    message: OutboundMessage,
    document: OutboundDocument,
    caption: str | None,
) -> bool:
    for text, parse_mode in _caption_attempts(caption):
        try:
            await bot.send_document(
                message.telegram_chat_id,
                _input_file(document),
                caption=text,
                parse_mode=parse_mode,
                reply_parameters=_reply_parameters(message),
            )
            return True
        except TelegramBadRequest as exc:
            _log_failure(message, document, exc)
        except Exception as exc:  # noqa: BLE001 - swallow Telegram I/O
            _log_failure(message, document, exc)
            return False
    return False


def _input_file(document: OutboundDocument) -> BufferedInputFile:
    return BufferedInputFile(
        document.content.encode("utf-8"), filename=document.file_name
    )


def _reply_parameters(message: OutboundMessage) -> ReplyParameters | None:
    if message.reply_to_message_id is None:
        return None
    return ReplyParameters(
        message_id=message.reply_to_message_id, allow_sending_without_reply=True
    )


def _log_failure(
    message: OutboundMessage, document: OutboundDocument, exc: BaseException
) -> None:
    # The type only: the error text may echo the caption.
    logger.warning(
        "outbound_document_failed chat_id=%s file=%s error=%s",
        message.telegram_chat_id,
        document.file_name,
        type(exc).__name__,
    )
