import logging

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message as TelegramMessage

from vanessa.infrastructure.observability.metrics import record_telegram

logger = logging.getLogger("services.bot.handlers.messages")


async def _emit_chat_text(
    telegram_message: TelegramMessage,
    text: str,
    *,
    as_reply: bool,
    parse_mode: ParseMode | None = None,
) -> None:
    send = telegram_message.reply if as_reply else telegram_message.answer
    if parse_mode is None:
        await send(text)
        return
    await send(text, parse_mode=parse_mode)


def _swallow_block_failure(
    telegram_message: TelegramMessage,
    *,
    index: int,
    total: int,
    exc: BaseException,
) -> None:
    logger.warning(
        "reply_block_failed chat_id=%s index=%s/%s error=%s",
        telegram_message.chat.id,
        index + 1,
        total,
        exc,
    )


async def _deliver_plain_fallback(
    telegram_message: TelegramMessage,
    plain: str,
    *,
    as_reply: bool,
    index: int,
    total: int,
) -> bool:
    try:
        await _emit_chat_text(telegram_message, plain, as_reply=as_reply)
        record_telegram("send_reply", "success")
        return True
    except Exception as exc:  # noqa: BLE001 - swallow Telegram I/O
        _swallow_block_failure(
            telegram_message, index=index, total=total, exc=exc
        )
        return False


async def _deliver_reply_block(
    telegram_message: TelegramMessage,
    *,
    html: str,
    plain: str,
    as_reply: bool,
    index: int,
    total: int,
) -> bool:
    """HTML first; plain text on ``TelegramBadRequest``; False stops the loop."""
    try:
        await _emit_chat_text(
            telegram_message,
            html,
            as_reply=as_reply,
            parse_mode=ParseMode.HTML,
        )
        record_telegram("send_reply", "success")
        return True
    except TelegramBadRequest:
        return await _deliver_plain_fallback(
            telegram_message,
            plain,
            as_reply=as_reply,
            index=index,
            total=total,
        )
    except Exception as exc:  # noqa: BLE001 - swallow Telegram I/O
        _swallow_block_failure(
            telegram_message, index=index, total=total, exc=exc
        )
        return False
