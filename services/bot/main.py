import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher

from services.bot.container import create_bot_services
from services.bot.handlers import create_router
from services.bot.middleware import BotLoggingMiddleware
from vanessa.config import settings
from vanessa.core.logging_setup import configure_logging
from vanessa.observability.alerting import create_alert_manager

configure_logging("bot")
logger = logging.getLogger(__name__)


async def main() -> None:
    from vanessa.observability.metrics import start_metrics_http_server

    start_metrics_http_server(settings.bot_metrics_port)
    logger.info(
        "bot health/metrics endpoint started on :%s",
        settings.bot_metrics_port,
    )

    alert_task: asyncio.Task | None = None
    alert_manager = create_alert_manager()
    if alert_manager is not None:
        alert_task = asyncio.create_task(alert_manager.run_forever())
        logger.info("AlertManager started (chat_id=%s)", settings.alerting_dev_chat_id)

    services = create_bot_services()
    bot = Bot(token=settings.telegram_bot_token)
    if services.stickers is not None:
        await services.stickers.resolve_file_ids(bot)
    me = await bot.get_me()
    logger.info("Bot started as @%s id=%s", me.username, me.id)
    dp = Dispatcher()
    router = create_router(services)
    router.message.middleware(BotLoggingMiddleware())
    dp.include_router(router)

    # Graceful shutdown: aiogram's start_polling(handle_signals=True default)
    # already registers SIGINT/SIGTERM handlers that stop the polling loop
    # cooperatively and close the bot session (close_bot_session=True default).
    # We keep our own signal handler registration OUT so we don't shadow the
    # framework's, and rely on the finally block for final cleanup.
    logger.info("Bot polling started")
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Bot polling stopped, cleaning up")
        if alert_task is not None:
            alert_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await alert_task
        with contextlib.suppress(Exception):
            await bot.session.close()
        logger.info("Bot shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
