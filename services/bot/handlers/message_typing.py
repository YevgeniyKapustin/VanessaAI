import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from aiogram import Bot

from vanessa.infrastructure.observability.metrics import (
    record_telegram,
    record_telegram_error,
)

logger = logging.getLogger("services.bot.handlers.messages")

_TYPING_INTERVAL_SECONDS = 4.0

_TELEGRAM_ERROR_TYPES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("retryafter", "flood"), "flood"),
    (("forbidden",), "blocked"),
    (("badrequest", "conflict"), "bad_request"),
    (("migrate",), "migrate"),
)


def _telegram_error_type(exc: Exception) -> str:
    """Coarse error class for the Telegram error metric.

    ``flood`` = 429 rate-limit / RetryAfter (Telegram flood control),
    ``blocked`` = 403 Forbidden (the user blocked the bot). Both feed the
    dedicated ``vanessa_telegram_rate_limits_total`` counter so they surface
    separately from generic ``bad_request`` / ``network`` errors.
    """
    return _classify_telegram_error(type(exc).__name__.lower())


def _classify_telegram_error(name: str) -> str:
    for markers, error_type in _TELEGRAM_ERROR_TYPES:
        if any(marker in name for marker in markers):
            return error_type
    return "network"


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
    except Exception as exc:  # noqa: BLE001 - typing is best-effort
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
    loop for the whole duration of a slow Gate -> Retrieve -> Compose
    request (2-6s+). Each ping is guarded individually: a single
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
        except Exception as exc:  # noqa: BLE001 - typing is best-effort
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
