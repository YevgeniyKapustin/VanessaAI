from aiogram import Router

from services.bot.container import BotServices
from services.bot.handlers.messages import create_messages_router
from services.bot.handlers.notes import create_notes_router


def create_router(services: BotServices) -> Router:
    router = Router()
    router.include_router(create_notes_router(services))
    router.include_router(create_messages_router(services))
    return router
