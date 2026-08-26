import io
import logging
from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message as TelegramMessage

from app.bot.container import BotServices
from app.bot.messages import IncomingMessage
from app.knowledge.format import INBOX, TYPE_NOTE, today

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

        if not services.knowledge.is_configured:
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
            await services.knowledge.ensure_structure()
            stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d_%H%M%S")
            note_path = f"{INBOX}/{stamp}.md"

            body_parts: list[str] = []
            if text:
                body_parts.append(text)
            if attachment_bytes:
                suffix = (
                    attachment_suffix
                    if attachment_suffix.startswith(".")
                    else f".{attachment_suffix}"
                )
                attachment_rel = f"{INBOX}/attachments/{stamp}{suffix}"
                await services.knowledge.write_attachment(attachment_rel, attachment_bytes)
                body_parts.append(f"![[{attachment_rel}]]")

            saved = await services.knowledge.write_note(
                note_path,
                {"type": TYPE_NOTE, "date": today(), "tags": [INBOX]},
                "\n\n".join(body_parts),
            )
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
