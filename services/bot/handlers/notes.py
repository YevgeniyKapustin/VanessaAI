import io
import logging

import httpx
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message as TelegramMessage

from services.bot.container import BotServices
from services.bot.messages import IncomingMessage

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

        text = (command.args or "").strip()
        attachment_bytes: bytes | None = None
        attachment_suffix = ".jpg"

        if telegram_message.photo:
            photo = telegram_message.photo[-1]
            buffer = io.BytesIO()
            await telegram_message.bot.download(photo, destination=buffer)
            attachment_bytes = buffer.getvalue()

        if not text and not attachment_bytes:
            await telegram_message.answer(services.texts.notes.empty.strip())
            return

        try:
            saved = await services.notes_client.save_inbox_note(
                text=text,
                attachment_bytes=attachment_bytes,
                attachment_suffix=attachment_suffix,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 503:
                await telegram_message.answer(
                    services.texts.notes.not_configured.strip()
                )
                return
            logger.exception(
                "knowledge_note_failed chat_id=%s sender_id=%s",
                incoming.telegram_chat_id,
                incoming.sender_telegram_id,
            )
            await telegram_message.answer(
                services.texts.notes.error.format(detail=str(exc)).strip()
            )
            return
        except Exception as exc:
            logger.exception(
                "knowledge_note_failed chat_id=%s sender_id=%s",
                incoming.telegram_chat_id,
                incoming.sender_telegram_id,
            )
            await telegram_message.answer(
                services.texts.notes.error.format(detail=str(exc)).strip()
            )
            return

        await telegram_message.answer(
            services.texts.notes.success.format(filename=saved).strip()
        )
        logger.info(
            "knowledge_note_ok chat_id=%s path=%s",
            incoming.telegram_chat_id,
            saved,
        )

    return router
