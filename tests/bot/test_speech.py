from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import BufferedInputFile

from services.bot.container import BotServices, create_bot_services
from services.bot.handlers.message_speech import maybe_send_voice, omit_text_after_voice
from services.bot.messages.response import ChatProcessResult
from services.bot.services.broker_client import BrokerTurnClient
from services.bot.speech_settings import resolve_telegram_speech_enabled
from tests.bot.test_bot_message import make_telegram_message
from vanessa.config.channels import load_channel_profile
from vanessa.config.content import get_content
from vanessa.config.settings_sections import BotMixin
from vanessa.core.protocols.speech import SpeechAudio


def test_telegram_speech_defaults_off() -> None:
    assert BotMixin.speech_enabled is False
    assert BotMixin.speech_send == "voice_and_text"


def test_create_bot_services_does_not_wire_speech() -> None:
    services = create_bot_services()
    assert isinstance(services.chat_client, BrokerTurnClient)
    assert services.speech_enabled is False
    assert services.speech is None
    assert services.speech_send == "voice_and_text"


def test_channel_yaml_speech_false_wins(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    path.write_text("speech: false\nstickers: true\n", encoding="utf-8")
    assert (
        resolve_telegram_speech_enabled(default=True, channels_path=path) is False
    )


def test_channel_yaml_speech_true_is_respected(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    path.write_text("speech: true\n", encoding="utf-8")
    assert resolve_telegram_speech_enabled(default=False, channels_path=path) is True


def test_channel_profile_speech_is_off() -> None:
    assert load_channel_profile("telegram").speech is False


def test_missing_channel_yaml_uses_default(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    assert resolve_telegram_speech_enabled(default=False, channels_path=path) is False


def test_omit_text_only_after_successful_voice_only() -> None:
    assert omit_text_after_voice(voice_sent=True, speech_send="voice_only") is True
    assert omit_text_after_voice(voice_sent=False, speech_send="voice_only") is False
    assert omit_text_after_voice(voice_sent=True, speech_send="voice_and_text") is False


def _speech_services(
    *,
    enabled: bool = True,
    speech_send: str = "voice_and_text",
    synthesizer: MagicMock | None = None,
) -> BotServices:
    return BotServices(
        chat_client=AsyncMock(),
        notes_client=AsyncMock(),
        access_guard=AsyncMock(),
        texts=get_content().bot,
        speech=synthesizer,
        speech_enabled=enabled,
        speech_send=speech_send,
    )


def _reply(text: str = "Да?") -> ChatProcessResult:
    return ChatProcessResult(action="reply", reason="intent", reply=text)


@pytest.mark.asyncio
async def test_maybe_send_voice_noop_when_disabled() -> None:
    message = make_telegram_message()
    message.bot.send_voice = AsyncMock()
    synthesizer = AsyncMock()
    services = _speech_services(enabled=False, synthesizer=synthesizer)
    sent = await maybe_send_voice(message, _reply(), services)
    assert sent is False
    synthesizer.synthesize.assert_not_awaited()
    message.bot.send_voice.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_send_voice_uploads_wav_when_enabled() -> None:
    message = make_telegram_message()
    message.bot.send_voice = AsyncMock()
    synthesizer = AsyncMock()
    synthesizer.synthesize = AsyncMock(
        return_value=SpeechAudio(pcm=b"\x00\x10", sample_rate=16_000)
    )
    services = _speech_services(synthesizer=synthesizer)
    sent = await maybe_send_voice(message, _reply("привет"), services)
    assert sent is True
    synthesizer.synthesize.assert_awaited_once_with("привет")
    message.bot.send_voice.assert_awaited_once()
    kwargs = message.bot.send_voice.await_args.kwargs
    voice = kwargs["voice"]
    assert isinstance(voice, BufferedInputFile)
    assert voice.filename == "voice.wav"
    assert voice.data.startswith(b"RIFF")


@pytest.mark.asyncio
async def test_maybe_send_voice_swallows_tts_errors() -> None:
    message = make_telegram_message()
    message.bot.send_voice = AsyncMock()
    synthesizer = AsyncMock()
    synthesizer.synthesize = AsyncMock(side_effect=RuntimeError("down"))
    services = _speech_services(synthesizer=synthesizer)
    sent = await maybe_send_voice(message, _reply(), services)
    assert sent is False
    message.bot.send_voice.assert_not_awaited()
