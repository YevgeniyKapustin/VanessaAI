import io
import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message as TelegramMessage

from services.bot.container import BotServices
from services.bot.messages import IncomingMessage
from services.bot.services.broker_client import NotesError

logger = logging.getLogger(__name__)


def create_notes_router(services: BotServices) -> Router:
    router = Router()

    @router.message(Command("note"))
    async def cmd_note(
        telegram_message: TelegramMessage,
        command: CommandObject,
    ) -> None:
        await _run_cmd_note(services, telegram_message, command)

    return router


async def _run_cmd_note(
    services: BotServices,
    telegram_message: TelegramMessage,
    command: CommandObject,
) -> None:
    incoming = IncomingMessage.from_telegram(telegram_message)
    error = services.access_guard.ensure_owner_dm(incoming)
    if error:
        await telegram_message.answer(error)
        return
    text, attachment_bytes = await _note_payload(telegram_message, command)
    if not text and not attachment_bytes:
        await telegram_message.answer(services.texts.notes.empty.strip())
        return
    await _save_note(
        services, telegram_message, incoming, text, attachment_bytes
    )


async def _note_payload(
    telegram_message: TelegramMessage,
    command: CommandObject,
) -> tuple[str, bytes | None]:
    text = (command.args or "").strip()
    if not telegram_message.photo:
        return text, None
    photo = telegram_message.photo[-1]
    buffer = io.BytesIO()
    await telegram_message.bot.download(photo, destination=buffer)
    return text, buffer.getvalue()


async def _save_note(
    services: BotServices,
    telegram_message: TelegramMessage,
    incoming: IncomingMessage,
    text: str,
    attachment_bytes: bytes | None,
) -> None:
    try:
        saved = await services.notes_client.save_inbox_note(
            text=text,
            attachment_bytes=attachment_bytes,
            attachment_suffix=".jpg",
        )
    except NotesError as exc:
        if exc.code == "knowledge_not_configured":
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
            services.texts.notes.error.format(detail=exc.code).strip()
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

