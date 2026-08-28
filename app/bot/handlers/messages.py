import asyncio
import base64
import contextlib
import io
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, Message as TelegramMessage, PhotoSize

from app.bot.container import BotServices
from app.bot.messages import IncomingMessage
from app.bot.stickers.heuristics import is_sticker_request
from app.bot.telegram_format import markdown_to_telegram_html
from app.config.settings import settings
from app.core.messages import ImageAttachment
from app.decision.models import DecisionAction
from app.observability.metrics import (
    record_photo_send,
    record_telegram,
    record_telegram_error,
)

logger = logging.getLogger(__name__)

_PREVIEW_LEN = 80


def _telegram_error_type(exc: Exception) -> str:
    """Coarse error class for the Telegram error metric.

    ``flood`` = 429 rate-limit / RetryAfter (Telegram flood control),
    ``blocked`` = 403 Forbidden (the user blocked the bot). Both feed the
    dedicated ``vanessa_telegram_rate_limits_total`` counter so they surface
    separately from generic ``bad_request`` / ``network`` errors.
    """
    name = type(exc).__name__.lower()
    if "retryafter" in name or "flood" in name:
        return "flood"
    if "forbidden" in name:
        return "blocked"
    if "badrequest" in name or "conflict" in name:
        return "bad_request"
    if "migrate" in name:
        return "migrate"
    return "network"


def _preview(text: str) -> str:
    normalized = text.replace("\n", " ").strip()
    if len(normalized) <= _PREVIEW_LEN:
        return normalized
    return f"{normalized[:_PREVIEW_LEN]}..."


async def _send_reply(telegram_message: TelegramMessage, reply: str) -> None:
    formatted = markdown_to_telegram_html(reply)
    try:
        await telegram_message.reply(formatted, parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        await telegram_message.reply(reply)
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
    for index, block in enumerate(messages):
        if index > 0 and delay > 0:
            await asyncio.sleep(delay)
        formatted = markdown_to_telegram_html(block)
        try:
            if index == 0:
                await telegram_message.reply(formatted, parse_mode=ParseMode.HTML)
            else:
                await telegram_message.answer(formatted, parse_mode=ParseMode.HTML)
            record_telegram("send_reply", "success")
        except TelegramBadRequest:
            try:
                if index == 0:
                    await telegram_message.reply(block)
                else:
                    await telegram_message.answer(block)
                record_telegram("send_reply", "success")
            except Exception as exc:
                logger.warning(
                    "reply_block_failed chat_id=%s index=%s/%s error=%s",
                    telegram_message.chat.id,
                    index + 1,
                    len(messages),
                    exc,
                )
                break
        except Exception as exc:
            logger.warning(
                "reply_block_failed chat_id=%s index=%s/%s error=%s",
                telegram_message.chat.id,
                index + 1,
                len(messages),
                exc,
            )
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
    except Exception as exc:
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
        except Exception as exc:
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


_TYPING_INTERVAL_SECONDS = 4.0


async def _ping_typing(bot: Bot, chat_id: int, where: str) -> None:
    """Send one Telegram "typing" action, logging the outcome for diagnostics.

    A failure (e.g. Telegram 429 flood control or a transient network error)
    only drops the indicator — it must never break the reply path. Every ping
    is logged (DEBUG on success, WARNING on failure) so production behaviour is
    observable in the timestamped bot log.
    """
    try:
        await bot.send_chat_action(chat_id, "typing")
        record_telegram("typing", "success")
        logger.debug("typing_ping chat_id=%s where=%s", chat_id, where)
    except Exception as exc:
        record_telegram("typing", "error")
        record_telegram_error("typing", _telegram_error_type(exc))
        logger.warning(
            "typing_ping_failed chat_id=%s where=%s error=%s",
            chat_id,
            where,
            exc,
        )


async def _typing_loop(
    bot: Bot,
    chat_id: int,
    interval: float = _TYPING_INTERVAL_SECONDS,
) -> None:
    """Re-send the Telegram "typing" action while the pipeline runs.

    Telegram's typing state expires after ~5s, so it must be refreshed in a
    loop for the whole duration of a slow Gate -> Retrieve -> Compose ->
    Critique request (2-6s+). Each ping is guarded individually: a single
    failed ping (e.g. Telegram 429 flood control or a transient network error)
    must NOT stop the indicator for the rest of the turn, so this loop only
    exits via cancellation from _typing_on_signal. After consecutive failures
    we back off (up to 3x the interval) so a dead chat isn't hammered.
    asyncio.CancelledError is a BaseException (not an Exception), so cancelling
    this task stops it cleanly.
    """
    consecutive_failures = 0
    while True:
        try:
            await bot.send_chat_action(chat_id, "typing")
            consecutive_failures = 0
            record_telegram("typing", "success")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            consecutive_failures += 1
            record_telegram("typing", "error")
            record_telegram_error("typing", _telegram_error_type(exc))
            logger.warning(
                "typing_ping_failed chat_id=%s consecutive_failures=%s error=%s",
                chat_id,
                consecutive_failures,
                exc,
            )
        backoff = min(consecutive_failures, 3)
        await asyncio.sleep(interval * max(backoff, 1))


@contextlib.asynccontextmanager
async def _typing_on_signal(
    bot: Bot,
    chat_id: int,
    interval: float = _TYPING_INTERVAL_SECONDS,
) -> AsyncIterator[Callable[[], Awaitable[None]]]:
    """Show a live "typing..." indicator only after the API signals a reply.

    Vanessa starts "typing" the moment the decision gate has passed and she
    commits to an actual answer: the yielded trigger is fired by the API SSE
    stream (``on_started``) at exactly that point. Until then no "typing" is
    shown, so messages she will ignore never pretend she is writing. Once
    fired, a first ping goes out right away and a background task keeps
    refreshing it (Telegram's typing state expires after ~5s) for the rest of
    the turn. The task is cancelled on exit, covering success, error and
    early-return paths. Telegram-side failures only drop the indicator, never
    the reply.
    """
    trigger = asyncio.Event()
    typing_task: asyncio.Task | None = None

    async def _start() -> None:
        nonlocal typing_task
        if typing_task is not None:
            return
        await _ping_typing(bot, chat_id, "start")
        typing_task = asyncio.create_task(_typing_loop(bot, chat_id, interval))

    try:
        yield _start
    finally:
        if typing_task is not None:
            typing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await typing_task


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
    except Exception as exc:
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


def create_messages_router(services: BotServices) -> Router:
    router = Router()

    async def _reject_if_no_access(
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

    @router.message(CommandStart())
    async def cmd_start(telegram_message: TelegramMessage) -> None:
        incoming = IncomingMessage.from_telegram(telegram_message)
        if await _reject_if_no_access(telegram_message, incoming):
            return
        logger.info(
            "command_start chat_id=%s sender_id=%s",
            incoming.telegram_chat_id,
            incoming.sender_telegram_id,
        )
        await telegram_message.answer(services.texts.welcome.strip())
        if services.stickers is not None:
            services.stickers.register_reply(incoming.telegram_chat_id)
            await services.stickers.send_if_any(
                telegram_message,
                sticker_tag="greeting",
            )

    @router.message(F.text)
    async def handle_text(telegram_message: TelegramMessage) -> None:
        incoming = IncomingMessage.from_telegram(telegram_message)
        # "typing..." starts only once the API signals that the decision gate
        # has passed and Vanessa is composing an actual answer (SSE "started"
        # event). Messages she will ignore never trigger it.
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
        if await _reject_if_no_access(telegram_message, incoming):
            return

        logger.info(
            "message_received chat_id=%s sender_id=%s text=%r",
            incoming.telegram_chat_id,
            incoming.sender_telegram_id,
            _preview(incoming.text),
        )

        try:
            result = await services.chat_client.process(
                incoming,
                on_started=start_typing,
            )
        except httpx.HTTPError as exc:
            # Never leak errors into the chat: log the failure and drop the
            # turn silently instead of spamming the conversation.
            logger.warning(
                "api_request_error chat_id=%s error=%s",
                incoming.telegram_chat_id,
                exc,
            )
            return

        if result.action != DecisionAction.REPLY or (
            not result.reply and not result.sticker_tag
        ):
            logger.info(
                "message_ignored chat_id=%s reason=%s relevance=%.3f",
                incoming.telegram_chat_id,
                result.reason,
                result.relevance_score,
            )
            return

        sticker_only = (
            services.stickers is not None
            and services.stickers.is_sticker_only(result.sticker_tag)
        )
        if sticker_only:
            # The sticker itself is the whole reply — it already carries a caption
            # on the image, so no text accompanies it. Send it forced: the sticker
            # IS the reply, the anti-spam gate must not swallow the only thing we
            # send. If the sticker can't be sent, fall back to the text answer.
            services.stickers.register_reply(incoming.telegram_chat_id)
            # Refresh "typing..." right before the reply is delivered so the
            # indicator never dies in the tail of the pipeline.
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
            if sent is None:
                if result.reply:
                    await _send_reply(telegram_message, result.reply)
                else:
                    # The sticker could not be delivered and there is no text
                    # answer to fall back on — send nothing, but surface the
                    # failure so a "nothing was sent" turn stays observable.
                    logger.warning(
                        "sticker_only_failed chat_id=%s tag=%s no_text_fallback",
                        incoming.telegram_chat_id,
                        result.sticker_tag,
                    )
            return

        # Refresh "typing..." right before the reply is delivered so the
        # indicator never dies in the tail of the pipeline.
        await _ping_typing(
            telegram_message.bot, incoming.telegram_chat_id, "pre_reply"
        )
        # Prefer the model-marked block list; fall back to the single reply.
        # ``max_messages`` is a safety cap so a runaway model can never flood
        # the chat (0 = no cap).
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
        # The compose model asked to re-send a photo from the album: deliver it
        # after the text (so the text reads like a normal reply). The data_url is
        # the stored-bytes fallback when the Telegram file_id is stale.
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
            # A direct request («кинь стикер») must always be honoured: bypass
            # the anti-spam probability roll and the cooldown.
            await services.stickers.send_if_any(
                telegram_message,
                sticker_tag=result.sticker_tag,
                reply_text=result.reply,
                force=is_sticker_request(incoming.text),
            )

    @router.message(F.photo)
    async def handle_photo(telegram_message: TelegramMessage) -> None:
        """Handle photos (with or without a caption) via the vision pipeline.

        The bot auto-replies to ANY photo in an allowed chat: the image is
        downloaded by file_id, base64-encoded and sent to the API, which routes
        the turn to the DeepSeek vision model. A photo with a caption uses the
        caption as the message text; a bare photo uses the placeholder.
        """
        if not settings.vision_enabled:
            # Vision off: treat the photo as its caption only (bare photos are
            # dropped, captions flow through the normal text pipeline).
            caption = (telegram_message.caption or "").strip()
            if not caption:
                logger.info(
                    "photo_ignored_vision_disabled chat_id=%s",
                    telegram_message.chat.id,
                )
                return
            incoming = IncomingMessage.from_telegram(
                telegram_message,
                text=caption[:4096],
            )
            async with _typing_on_signal(
                telegram_message.bot,
                incoming.telegram_chat_id,
                interval=services.typing_interval_seconds,
            ) as start_typing:
                await _handle_text_core(
                    telegram_message, incoming, services, start_typing
                )
            return

        images = await _download_photo_images(
            telegram_message,
            max_bytes=settings.vision_max_image_bytes,
        )
        caption = (telegram_message.caption or "").strip()
        if not images:
            # Download/encode failed: fall back to the caption (if any) so the
            # photo is not silently lost; a bare photo is dropped with a log.
            if not caption:
                logger.warning(
                    "photo_dropped_download_failed chat_id=%s",
                    telegram_message.chat.id,
                )
                return
            incoming = IncomingMessage.from_telegram(
                telegram_message,
                text=caption[:4096],
            )
        else:
            incoming = IncomingMessage.from_telegram(
                telegram_message,
                images=tuple(images),
                text=(caption or settings.vision_photo_placeholder)[:4096],
            )

        async with _typing_on_signal(
            telegram_message.bot,
            incoming.telegram_chat_id,
            interval=services.typing_interval_seconds,
        ) as start_typing:
            await _handle_text_core(
                telegram_message, incoming, services, start_typing
            )

    return router
