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
from vanessa.infrastructure.speech import ElevenLabsSpeech

_PCM = b"\x00\x10"
_MP3 = b"ID3\x03"


def test_telegram_speech_defaults_are_opt_in() -> None:
    assert BotMixin.speech_enabled is False
    assert BotMixin.speech_send == "on_request"


def test_create_bot_services_wires_speech_from_env_and_channel() -> None:
    services = create_bot_services()
    assert isinstance(services.chat_client, BrokerTurnClient)
    assert services.speech_enabled is True
    assert isinstance(services.speech, ElevenLabsSpeech)
    # One client, both directions: TTS for replies, STT for incoming notes.
    assert services.speech_transcriber is services.speech
    assert services.speech_format == "mp3_44100_128"


def test_channel_yaml_speech_false_wins(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    path.write_text("speech: false\nstickers: true\n", encoding="utf-8")
    assert (
        resolve_telegram_speech_enabled(default=True, channels_path=path) is False
    )


def test_speech_env_switch_disables_enabled_channel(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    path.write_text("speech: true\n", encoding="utf-8")
    assert resolve_telegram_speech_enabled(default=False, channels_path=path) is False


def test_channel_yaml_speech_true_with_env_on(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    path.write_text("speech: true\n", encoding="utf-8")
    assert resolve_telegram_speech_enabled(default=True, channels_path=path) is True


def test_channel_profile_telegram_speaks() -> None:
    assert load_channel_profile("telegram").speech is True


def test_missing_channel_yaml_uses_default(tmp_path: Path) -> None:
    path = tmp_path / "telegram.yaml"
    assert resolve_telegram_speech_enabled(default=False, channels_path=path) is False


def test_omit_text_only_outside_voice_and_text() -> None:
    assert omit_text_after_voice(voice_sent=True, speech_send="on_request") is True
    assert omit_text_after_voice(voice_sent=True, speech_send="voice_only") is True
    assert omit_text_after_voice(voice_sent=False, speech_send="voice_only") is False
    assert (
        omit_text_after_voice(voice_sent=True, speech_send="voice_and_text") is False
    )


def _speech_services(
    *,
    enabled: bool = True,
    speech_send: str = "on_request",
    speech_format: str = "mp3_44100_128",
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
        speech_format=speech_format,
    )


def _reply(text: str = "Да?") -> ChatProcessResult:
    return ChatProcessResult(action="reply", reason="intent", reply=text)


def _message() -> MagicMock:
    message = make_telegram_message()
    message.bot.send_voice = AsyncMock()
    return message


def _synthesizer(payload: bytes = _MP3) -> AsyncMock:
    synthesizer = AsyncMock()
    synthesizer.synthesize = AsyncMock(
        return_value=SpeechAudio(pcm=payload, sample_rate=44_100)
    )
    return synthesizer


@pytest.mark.asyncio
async def test_maybe_send_voice_noop_when_disabled() -> None:
    message = _message()
    synthesizer = _synthesizer()
    services = _speech_services(enabled=False, synthesizer=synthesizer)
    sent = await maybe_send_voice(message, _reply(), services, requested=True)
    assert sent is False
    synthesizer.synthesize.assert_not_awaited()
    message.bot.send_voice.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_send_voice_waits_for_a_trigger() -> None:
    message = _message()
    synthesizer = _synthesizer()
    services = _speech_services(synthesizer=synthesizer)
    sent = await maybe_send_voice(message, _reply(), services)
    assert sent is False
    synthesizer.synthesize.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_send_voice_uploads_mp3_on_request() -> None:
    message = _message()
    synthesizer = _synthesizer()
    services = _speech_services(synthesizer=synthesizer)
    sent = await maybe_send_voice(
        message, _reply("**привет**"), services, requested=True
    )
    assert sent is True
    synthesizer.synthesize.assert_awaited_once_with("привет")
    voice = message.bot.send_voice.await_args.kwargs["voice"]
    assert isinstance(voice, BufferedInputFile)
    assert voice.filename == "voice.mp3"
    assert voice.data == _MP3


@pytest.mark.asyncio
async def test_maybe_send_voice_answers_a_voice_note() -> None:
    message = _message()
    services = _speech_services(synthesizer=_synthesizer())
    sent = await maybe_send_voice(
        message, _reply("ага"), services, replied_to_voice=True
    )
    assert sent is True
    message.bot.send_voice.assert_awaited_once()


@pytest.mark.asyncio
async def test_maybe_send_voice_wraps_pcm_when_configured() -> None:
    message = _message()
    services = _speech_services(
        speech_format="pcm_24000",
        synthesizer=_synthesizer(_PCM),
    )
    sent = await maybe_send_voice(message, _reply("привет"), services, requested=True)
    assert sent is True
    voice = message.bot.send_voice.await_args.kwargs["voice"]
    assert voice.filename == "voice.wav"
    assert voice.data.startswith(b"RIFF")


@pytest.mark.asyncio
async def test_maybe_send_voice_swallows_tts_errors() -> None:
    message = _message()
    synthesizer = AsyncMock()
    synthesizer.synthesize = AsyncMock(side_effect=RuntimeError("down"))
    services = _speech_services(synthesizer=synthesizer)
    sent = await maybe_send_voice(message, _reply(), services, requested=True)
    assert sent is False
    message.bot.send_voice.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_send_voice_skips_empty_audio() -> None:
    message = _message()
    services = _speech_services(synthesizer=_synthesizer(b""))
    assert await maybe_send_voice(message, _reply(), services, requested=True) is False
    message.bot.send_voice.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_send_voice_skips_markdown_only_reply() -> None:
    message = _message()
    services = _speech_services(synthesizer=_synthesizer())
    sent = await maybe_send_voice(message, _reply("***"), services, requested=True)
    assert sent is False


@pytest.mark.asyncio
async def test_maybe_send_voice_survives_telegram_refusal() -> None:
    message = _message()
    message.bot.send_voice = AsyncMock(side_effect=RuntimeError("blocked"))
    services = _speech_services(synthesizer=_synthesizer())
    sent = await maybe_send_voice(message, _reply("привет"), services, requested=True)
    assert sent is False
