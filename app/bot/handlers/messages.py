import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import Message as TelegramMessage

from app.bot.container import BotServices
from app.bot.messages import IncomingMessage
from app.bot.stickers.heuristics import is_sticker_request
from app.bot.telegram_format import markdown_to_telegram_html
from app.decision.models import DecisionAction
from app.observability.metrics import record_telegram, record_telegram_error

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

        if result.action != DecisionAction.REPLY or not result.reply:
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
                await _send_reply(telegram_message, result.reply)
            return

        # Refresh "typing..." right before the reply is delivered so the
        # indicator never dies in the tail of the pipeline.
        await _ping_typing(
            telegram_message.bot, incoming.telegram_chat_id, "pre_reply"
        )
        await _send_reply(telegram_message, result.reply)
        logger.info(
            "reply_sent chat_id=%s reply_len=%s",
            incoming.telegram_chat_id,
            len(result.reply),
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

    return router
