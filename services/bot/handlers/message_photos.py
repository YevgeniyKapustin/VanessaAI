import base64
import io
import logging
from functools import partial

from aiogram import Bot, F, Router
from aiogram.types import Message as TelegramMessage
from aiogram.types import PhotoSize

from services.bot.container import BotServices
from services.bot.handlers.message_delivery import _preview, _run_with_typing
from services.bot.media_groups import MediaGroupBuffer, MediaGroupFlushCallback
from services.bot.messages import IncomingMessage
from vanessa.config.content import get_photo_placeholder
from vanessa.config.settings import settings
from vanessa.core.messages import ImageAttachment

logger = logging.getLogger("services.bot.handlers.messages")


def _pick_photo_size(sizes: list[PhotoSize], max_bytes: int) -> PhotoSize | None:
    """Pick the largest Telegram photo size whose raw bytes fit ``max_bytes``.

    Telegram provides several resized copies of every photo; the vision model
    auto-resizes to ~800x800 anyway, so a size within the cap keeps the API body
    and the DB attachment column bounded. When every size exceeds the cap, the
    smallest is used as a best-effort fallback (still small enough in practice).
    """
    if not sizes:
        return None
    fitting = [size for size in sizes if size.file_size is not None and size.file_size <= max_bytes]
    if fitting:
        return max(fitting, key=lambda size: size.file_size or 0)
    return min(sizes, key=lambda size: size.file_size or 0)


async def _photo_to_attachment(bot: Bot, photo: PhotoSize) -> ImageAttachment | None:
    """Download one Telegram photo size and encode it as a base64 data URL."""
    try:
        buffer = io.BytesIO()
        await bot.download(photo, destination=buffer)
        raw = buffer.getvalue()
    except Exception as exc:  # noqa: BLE001 - skip a broken photo download
        logger.warning(
            "photo_download_failed file_id=%s error=%s",
            photo.file_id,
            exc,
        )
        return None
    if not raw:
        logger.warning("photo_download_empty file_id=%s", photo.file_id)
        return None
    mime_type = "image/jpeg"  # Telegram photos are JPEG
    data_url = f"data:{mime_type};base64,{base64.b64encode(raw).decode('ascii')}"
    return ImageAttachment(
        data_url=data_url,
        mime_type=mime_type,
        telegram_file_id=photo.file_id,
    )


async def _download_photo_images(
    telegram_message: TelegramMessage,
    *,
    max_bytes: int,
) -> list[ImageAttachment]:
    """Download the best-fitting size of each attached photo as data URLs.

    Failures are per-photo: a broken download is logged and skipped, never
    raised — a photo that can't be read simply becomes a caption-only turn.
    """
    sizes = list(telegram_message.photo or [])
    if not sizes:
        return []
    photo = _pick_photo_size(sizes, max_bytes)
    if photo is None:
        return []
    attachment = await _photo_to_attachment(telegram_message.bot, photo)
    if attachment is None:
        return []
    return [attachment]


def _caption_incoming(
    telegram_message: TelegramMessage,
    caption: str,
) -> IncomingMessage:
    return IncomingMessage.from_telegram(
        telegram_message,
        text=caption[:4096],
    )


async def _process_media_group(entry, services: BotServices) -> None:
    """Flush a buffered media group as ONE vision turn with all photos."""
    messages = entry.messages
    images = entry.images
    primary = next(
        (message for message in messages if (message.caption or "").strip()),
        messages[0],
    )
    caption = (primary.caption or "").strip()
    text = (caption or get_photo_placeholder())[:4096]
    incoming = IncomingMessage.from_telegram(
        primary,
        images=tuple(images),
        text=text,
    )
    logger.info(
        "media_group_flush chat_id=%s media_group_id=%s photos=%s text=%r",
        incoming.telegram_chat_id,
        entry.media_group_id,
        len(images),
        _preview(text),
    )
    await _run_with_typing(primary, incoming, services)


async def _handle_photo_vision(
    telegram_message: TelegramMessage,
    services: BotServices,
    media_groups: MediaGroupBuffer,
    on_flush: MediaGroupFlushCallback,
) -> None:
    images = await _download_photo_images(
        telegram_message,
        max_bytes=settings.vision_max_image_bytes,
    )
    caption = (telegram_message.caption or "").strip()
    if telegram_message.media_group_id and images:
        await media_groups.add(
            telegram_message.chat.id,
            telegram_message.media_group_id,
            telegram_message,
            images,
            on_flush=on_flush,
        )
        return
    if not images:
        if not caption:
            logger.warning(
                "photo_dropped_download_failed chat_id=%s",
                telegram_message.chat.id,
            )
            return
        incoming = _caption_incoming(telegram_message, caption)
    else:
        incoming = IncomingMessage.from_telegram(
            telegram_message,
            images=tuple(images),
            text=(caption or get_photo_placeholder())[:4096],
        )
    await _run_with_typing(telegram_message, incoming, services)


def _register_photo_handler(router: Router, services: BotServices) -> None:
    media_groups = MediaGroupBuffer()
    on_flush = partial(_process_media_group, services=services)

    async def handle_photo(telegram_message: TelegramMessage) -> None:
        """Handle photos (with or without a caption) via the vision pipeline."""
        if not settings.vision_enabled:
            caption = (telegram_message.caption or "").strip()
            if not caption:
                logger.info(
                    "photo_ignored_vision_disabled chat_id=%s",
                    telegram_message.chat.id,
                )
                return
            incoming = _caption_incoming(telegram_message, caption)
            await _run_with_typing(telegram_message, incoming, services)
            return
        await _handle_photo_vision(
            telegram_message,
            services,
            media_groups,
            on_flush=on_flush,
        )

    router.message.register(handle_photo, F.photo)
