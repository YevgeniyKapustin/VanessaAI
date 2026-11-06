import logging

from aiogram.types import BufferedInputFile
from aiogram.types import Message as TelegramMessage

from services.bot.container import BotServices
from services.bot.messages.response import ChatProcessResult
from services.bot.speech_policy import omits_text, should_send_voice
from vanessa.core.protocols.speech import SpeechAudio, SpeechSynthesizer
from vanessa.infrastructure.observability.metrics import record_telegram
from vanessa.infrastructure.speech import speakable_text, voice_payload

logger = logging.getLogger("services.bot.handlers.messages")


def omit_text_after_voice(*, voice_sent: bool, speech_send: str) -> bool:
    return omits_text(voice_sent=voice_sent, mode=speech_send)


async def maybe_send_voice(
    telegram_message: TelegramMessage,
    result: ChatProcessResult,
    services: BotServices,
    *,
    requested: bool = False,
    replied_to_voice: bool = False,
) -> bool:
    """Send the reply as a voice note when this turn calls for one.

    Returns True only when Telegram accepted the voice note — the caller then
    knows whether the text reply may be dropped. Every failure (no API key, TTS
    error, empty audio, Telegram refusal) is False, so the reply falls back to
    plain text and the chat never goes silent.
    """
    if not should_send_voice(
        mode=services.speech_send,
        requested=requested,
        replied_to_voice=replied_to_voice,
    ):
        return False
    synthesizer = _speech_client(services)
    if synthesizer is None:
        return False
    text = speakable_text(result.reply)
    if not text:
        return False
    return await _send_synthesized_voice(telegram_message, text, synthesizer, services)


def _speech_client(services: BotServices) -> SpeechSynthesizer | None:
    if not services.speech_enabled:
        return None
    return services.speech


async def _send_synthesized_voice(
    telegram_message: TelegramMessage,
    text: str,
    synthesizer: SpeechSynthesizer,
    services: BotServices,
) -> bool:
    try:
        audio = await synthesizer.synthesize(text)
    except Exception as exc:  # noqa: BLE001 - swallow TTS I/O
        logger.warning(
            "speech_synthesize_failed chat_id=%s error=%s",
            telegram_message.chat.id,
            exc,
        )
        return False
    if audio is None or not audio.pcm:
        return False
    return await _upload_voice(telegram_message, audio, services.speech_format)


async def _upload_voice(
    telegram_message: TelegramMessage,
    audio: SpeechAudio,
    output_format: str,
) -> bool:
    payload, filename = voice_payload(audio, output_format=output_format)
    if not payload:
        return False
    try:
        await telegram_message.bot.send_voice(
            telegram_message.chat.id,
            voice=BufferedInputFile(payload, filename=filename),
        )
    except Exception as exc:  # noqa: BLE001 - swallow Telegram I/O
        record_telegram("send_voice", "error")
        logger.warning(
            "speech_send_failed chat_id=%s error=%s",
            telegram_message.chat.id,
            exc,
        )
        return False
    record_telegram("send_voice", "success")
    return True
