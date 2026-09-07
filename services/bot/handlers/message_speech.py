import logging

from aiogram.types import BufferedInputFile
from aiogram.types import Message as TelegramMessage

from services.bot.container import BotServices
from services.bot.messages.response import ChatProcessResult
from vanessa.core.protocols.speech import SpeechAudio, SpeechSynthesizer
from vanessa.infrastructure.observability.metrics import record_telegram
from vanessa.infrastructure.speech import pcm_to_wav

logger = logging.getLogger("services.bot.handlers.messages")

_VOICE_SEND_MODES = frozenset({"voice_and_text", "voice_only"})


def omit_text_after_voice(*, voice_sent: bool, speech_send: str) -> bool:
    return voice_sent and speech_send == "voice_only"


async def maybe_send_voice(
    telegram_message: TelegramMessage,
    result: ChatProcessResult,
    services: BotServices,
) -> bool:
    synthesizer = _speech_client(services)
    if synthesizer is None:
        return False
    text = (result.reply or "").strip()
    if not text:
        return False
    return await _send_synthesized_voice(telegram_message, text, synthesizer)


def _speech_client(services: BotServices) -> SpeechSynthesizer | None:
    if not services.speech_enabled or services.speech_send not in _VOICE_SEND_MODES:
        return None
    return services.speech


async def _send_synthesized_voice(
    telegram_message: TelegramMessage,
    text: str,
    synthesizer: SpeechSynthesizer,
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
    return await _upload_voice(telegram_message, audio)


async def _upload_voice(
    telegram_message: TelegramMessage,
    audio: SpeechAudio,
) -> bool:
    wav = pcm_to_wav(audio.pcm, audio.sample_rate)
    try:
        await telegram_message.bot.send_voice(
            telegram_message.chat.id,
            voice=BufferedInputFile(wav, filename="voice.wav"),
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
