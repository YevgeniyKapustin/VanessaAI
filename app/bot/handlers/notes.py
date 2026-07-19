import io
import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message as TelegramMessage

from app.bot.container import BotServices
from app.bot.messages import IncomingMessage

logger = logging.getLogger(__name__)


def create_notes_router(services: BotServices) -> Router:
    router = Router()

    @router.message(Command("note"))
    async def cmd_note(
        telegram_message: TelegramMessage,
        command: CommandObject,
    ) -> None:
        incoming = IncomingMessage.from_telegram(telegram_message)
        error = services.access_guard.ensure_owner_dm(incoming)
        if error:
            await telegram_message.answer(error)
            return

        if not services.notes.is_configured:
            await telegram_message.answer(services.texts.notes.not_configured.strip())
            return

        text = (command.args or "").strip()
        attachment_bytes: bytes | None = None
        attachment_suffix = ".jpg"

        if telegram_message.photo:
            photo = telegram_message.photo[-1]
            buffer = io.BytesIO()
            await telegram_message.bot.download(photo, destination=buffer)
            attachment_bytes = buffer.getvalue()
            attachment_suffix = ".jpg"

        if not text and not attachment_bytes:
            await telegram_message.answer(services.texts.notes.empty.strip())
            return

        try:
            saved = await services.notes.save_note(
                text,
                attachment_bytes=attachment_bytes,
                attachment_suffix=attachment_suffix,
            )
        except Exception as exc:
            logger.exception(
                "obsidian_note_failed chat_id=%s sender_id=%s",
                incoming.telegram_chat_id,
                incoming.sender_telegram_id,
            )
            await telegram_message.answer(
                services.texts.notes.error.format(detail=str(exc)).strip()
            )
            return

        await telegram_message.answer(
            services.texts.notes.success.format(filename=saved.relative_path).strip()
        )
        logger.info(
            "obsidian_note_ok chat_id=%s path=%s",
            incoming.telegram_chat_id,
            saved.relative_path,
        )

    return router
