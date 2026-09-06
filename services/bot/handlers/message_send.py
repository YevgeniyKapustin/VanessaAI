import asyncio
import base64
import logging

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile
from aiogram.types import Message as TelegramMessage

from services.bot.handlers.message_send_fallback import (
    _deliver_reply_block,
    _emit_chat_text,
)
from services.bot.telegram_format import markdown_to_telegram_html
from vanessa.infrastructure.observability.metrics import (
    record_photo_send,
    record_telegram,
)

logger = logging.getLogger("services.bot.handlers.messages")


async def _send_reply(telegram_message: TelegramMessage, reply: str) -> None:
    formatted = markdown_to_telegram_html(reply)
    try:
        await _emit_chat_text(
            telegram_message,
            formatted,
            as_reply=True,
            parse_mode=ParseMode.HTML,
        )
    except TelegramBadRequest:
        await _emit_chat_text(telegram_message, reply, as_reply=True)
    record_telegram("send_reply", "success")


async def _send_reply_messages(
    telegram_message: TelegramMessage,
    messages: list[str],
    *,
    delay: float = 0.0,
) -> None:
    """Send a reply split into several messages, one Telegram message each.

    The first block replies to the user's message; the following blocks are sent
    as plain messages in the same chat, so they read as a natural sequential
    reply. A small ``delay`` between blocks makes the bot look like she is
    writing them one by one ("по мере написания"). A hard failure (flood
    control, blocked chat, formatting that still fails after the plain-text
    fallback) stops the loop — the bot never hammers a chat it can't reach, and
    a mid-reply failure is logged, not raised.
    """
    total = len(messages)
    for index, block in enumerate(messages):
        if index > 0 and delay > 0:
            await asyncio.sleep(delay)
        html = markdown_to_telegram_html(block)
        delivered = await _deliver_reply_block(
            telegram_message,
            html=html,
            plain=block,
            as_reply=index == 0,
            index=index,
            total=total,
        )
        if not delivered:
            break


def _data_url_to_input_file(data_url: str):
    """Decode a ``data:image/...;base64,...`` URL into an aiogram input file.

    Returns ``None`` (and lets the caller fail visibly) when the payload is
    malformed or empty — the fallback must never crash the reply path.
    """
    if not data_url or "," not in data_url:
        return None
    raw = base64.b64decode(data_url.split(",", 1)[1], validate=False)
    if not raw:
        return None
    return BufferedInputFile(raw, filename="photo.jpg")


async def _send_photo(
    telegram_message: TelegramMessage,
    file_id: str,
    data_url: str | None = None,
) -> bool:
    """Deliver a photo to the chat; return True only when it actually arrived.

    Robust delivery so a "sent" claim can never silently lose the photo:
    1. re-send by Telegram ``file_id`` (costs no upload, works for any received
       photo);
    2. if that fails and the stored bytes are available, fall back to uploading
       them from ``data_url`` — Telegram file_ids expire, the DB copy does not;
    3. if both fail, tell the user plainly instead of leaving a fake "sent".
    """
    photo_input = _data_url_to_input_file(data_url) if data_url else None
    try:
        await telegram_message.bot.send_photo(telegram_message.chat.id, photo=file_id)
        record_telegram("send_photo", "success")
        record_photo_send("delivered")
        return True
    except Exception as exc:  # noqa: BLE001 - swallow Telegram I/O
        logger.warning(
            "photo_send_failed chat_id=%s error=%s fallback=%s",
            telegram_message.chat.id,
            exc,
            photo_input is not None,
        )

    if photo_input is not None:
        try:
            await telegram_message.bot.send_photo(
                telegram_message.chat.id, photo=photo_input
            )
            record_telegram("send_photo", "success")
            record_photo_send("delivered")
            return True
        except Exception as exc:  # noqa: BLE001 - swallow Telegram I/O
            record_telegram("send_photo", "error")
            logger.warning(
                "photo_send_fallback_failed chat_id=%s error=%s",
                telegram_message.chat.id,
                exc,
            )
    else:
        record_telegram("send_photo", "error")

    # Neither path worked: never leave the user believing a photo was sent.
    await _send_reply(
        telegram_message,
        "Не получилось отправить фото — оно устарело. Попробуй переслать его ещё раз.",
    )
    record_photo_send("failed")
    return False
