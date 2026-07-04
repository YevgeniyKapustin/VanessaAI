from aiogram import Router

from app.bot.container import BotServices
from app.bot.handlers.messages import create_messages_router


def create_router(services: BotServices) -> Router:
    router = Router()
    router.include_router(create_messages_router(services))
    return router
