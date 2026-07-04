import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot.container import create_bot_services
from app.bot.handlers import create_router
from app.bot.middleware import BotLoggingMiddleware
from app.config import settings
from app.core.logging_setup import configure_logging

configure_logging("bot")
logger = logging.getLogger(__name__)


async def main() -> None:
    services = create_bot_services()
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    router = create_router(services)
    router.message.middleware(BotLoggingMiddleware())
    dp.include_router(router)
    logger.info("Bot polling started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
