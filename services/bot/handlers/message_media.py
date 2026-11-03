"""Inbound stickers and GIFs — looked at with vision, not just by their emoji.

A Telegram sticker is a WebP/TGS/WebM file the vision model cannot read, and a
GIF arrives as an MP4. Both, however, always carry a ``thumbnail``: a JPEG
preview frame Telegram renders for the chat list. That frame is what we feed
to the vision model, exactly like a photo.
"""

import base64
import io
import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.types import Message as TelegramMessage

from services.bot.container import BotServices
from services.bot.handlers.message_delivery import _run_with_typing
from services.bot.messages import IncomingMessage
from vanessa.config.content import get_gif_placeholder, get_sticker_placeholder
from vanessa.config.settings import settings
from vanessa.core.messages import ImageAttachment
from vanessa.core.messages_attachments import KIND_GIF, KIND_STICKER

logger = logging.getLogger("services.bot.handlers.messages")


async def _preview_attachment(
    bot: Bot | None,
    preview: Any,
    *,
    kind: str,
    max_bytes: int,
) -> ImageAttachment | None:
    """Download a sticker/GIF preview frame and encode it as a data URL."""
    if bot is None or preview is None:
        return None
    if _too_big(preview, max_bytes):
        logger.info(
            "media_preview_skipped kind=%s size=%s cap=%s",
            kind,
            getattr(preview, "file_size", None),
            max_bytes,
        )
        return None
    raw = await _download_preview(bot, preview, kind)
    if not raw:
        return None
    mime_type = "image/jpeg"  # Telegram thumbnails are JPEG
    return ImageAttachment(
        data_url=f"data:{mime_type};base64,{base64.b64encode(raw).decode('ascii')}",
        mime_type=mime_type,
        telegram_file_id=getattr(preview, "file_id", None),
        kind=kind,
    )


def _too_big(preview: Any, max_bytes: int) -> bool:
    size = getattr(preview, "file_size", None)
    return size is not None and size > max_bytes


async def _download_preview(bot: Bot, preview: Any, kind: str) -> bytes | None:
    try:
        buffer = io.BytesIO()
        await bot.download(preview, destination=buffer)
        raw = buffer.getvalue()
    except Exception as exc:  # noqa: BLE001 - never break the bot on media
        logger.warning("media_preview_download_failed kind=%s error=%s", kind, exc)
        return None
    if not raw:
        logger.warning("media_preview_empty kind=%s", kind)
    return raw or None


def _sticker_text(sticker: Any) -> str:
    """``[стикер 🙂]`` — the placeholder that makes the gate treat it as media."""
    placeholder = get_sticker_placeholder()
    emoji = (getattr(sticker, "emoji", None) or "").strip()
    return f"{placeholder} {emoji}".strip()


async def _handle_sticker(
    services: BotServices, telegram_message: TelegramMessage
) -> None:
    sticker = telegram_message.sticker
    if not settings.vision_enabled:
        logger.info("sticker_ignored_vision_disabled chat_id=%s", telegram_message.chat.id)
        return
    attachment = await _preview_attachment(
        telegram_message.bot,
        getattr(sticker, "thumbnail", None),
        kind=KIND_STICKER,
        max_bytes=settings.vision_max_image_bytes,
    )
    if attachment is None:
        logger.info(
            "sticker_without_preview chat_id=%s set=%s",
            telegram_message.chat.id,
            getattr(sticker, "set_name", None),
        )
        return
    incoming = IncomingMessage.from_telegram(
        telegram_message,
        images=(attachment,),
        text=_sticker_text(sticker),
    )
    await _run_with_typing(telegram_message, incoming, services)


async def _handle_animation(
    services: BotServices, telegram_message: TelegramMessage
) -> None:
    caption = (telegram_message.caption or "").strip()
    attachment = None
    if settings.vision_enabled:
        attachment = await _preview_attachment(
            telegram_message.bot,
            getattr(telegram_message.animation, "thumbnail", None),
            kind=KIND_GIF,
            max_bytes=settings.vision_max_image_bytes,
        )
    if attachment is None:
        if not caption:
            logger.info("gif_dropped chat_id=%s", telegram_message.chat.id)
            return
        incoming = IncomingMessage.from_telegram(telegram_message, text=caption[:4096])
    else:
        incoming = IncomingMessage.from_telegram(
            telegram_message,
            images=(attachment,),
            text=(caption or get_gif_placeholder())[:4096],
        )
    await _run_with_typing(telegram_message, incoming, services)


def register_media_handlers(router: Router, services: BotServices) -> None:
    """Route stickers and GIFs through the vision pipeline."""

    async def handle_sticker(telegram_message: TelegramMessage) -> None:
        await _handle_sticker(services, telegram_message)

    async def handle_animation(telegram_message: TelegramMessage) -> None:
        await _handle_animation(services, telegram_message)

    router.message.register(handle_sticker, F.sticker)
    router.message.register(handle_animation, F.animation)
