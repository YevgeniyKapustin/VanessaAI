"""Incoming Telegram voice notes — speech becomes an ordinary text turn.

The transcript is what the agent sees, so a voice message needs no prompt
changes: gate, retrieval and compose work exactly as for typed text. Nothing
is answered when transcription is unavailable (no key, no audio, provider
error) — silent by default, like any other unreadable media.
"""

import io
import logging

from aiogram import F, Router
from aiogram.types import Message as TelegramMessage

from services.bot.container import BotServices
from services.bot.handlers.message_delivery import _run_with_typing
from services.bot.messages import IncomingMessage

logger = logging.getLogger("services.bot.handlers.messages")

_MAX_VOICE_BYTES = 20 * 1024 * 1024
_VOICE_FILENAME = "voice.ogg"


async def _download_voice(telegram_message: TelegramMessage) -> bytes | None:
    voice = telegram_message.voice
    if voice is None:
        return None
    size = getattr(voice, "file_size", None)
    if size is not None and size > _MAX_VOICE_BYTES:
        logger.info(
            "voice_skipped_too_big chat_id=%s size=%s",
            telegram_message.chat.id,
            size,
        )
        return None
    buffer = io.BytesIO()
    try:
        await telegram_message.bot.download(voice, destination=buffer)
    except Exception as exc:  # noqa: BLE001 - never break the bot on media
        logger.warning(
            "voice_download_failed chat_id=%s error=%s",
            telegram_message.chat.id,
            exc,
        )
        return None
    return buffer.getvalue() or None


async def _transcribe(
    services: BotServices,
    telegram_message: TelegramMessage,
) -> str | None:
    transcriber = services.speech_transcriber
    if transcriber is None:
        logger.info("voice_ignored_stt_off chat_id=%s", telegram_message.chat.id)
        return None
    audio = await _download_voice(telegram_message)
    if not audio:
        return None
    try:
        return await transcriber.transcribe(audio, filename=_VOICE_FILENAME)
    except Exception as exc:  # noqa: BLE001 - swallow STT I/O
        logger.warning(
            "voice_transcribe_failed chat_id=%s error=%s",
            telegram_message.chat.id,
            exc,
        )
        return None


async def _handle_voice(
    services: BotServices,
    telegram_message: TelegramMessage,
) -> None:
    transcript = await _transcribe(services, telegram_message)
    if not transcript:
        return
    logger.info(
        "voice_transcribed chat_id=%s chars=%s",
        telegram_message.chat.id,
        len(transcript),
    )
    incoming = IncomingMessage.from_telegram(
        telegram_message,
        text=transcript,
        voice=True,
    )
    await _run_with_typing(telegram_message, incoming, services)


def register_voice_handler(router: Router, services: BotServices) -> None:
    """Answer a voice note by its transcript, not by its audio."""

    async def handle_voice(telegram_message: TelegramMessage) -> None:
        await _handle_voice(services, telegram_message)

    router.message.register(handle_voice, F.voice)
