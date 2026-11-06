"""Incoming voice notes: download, transcribe, then run an ordinary text turn."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.bot.container import BotServices
from services.bot.handlers.message_voice import _handle_voice
from tests.bot.test_bot_message import make_telegram_message
from vanessa.config.content import get_content

_VOICE_BYTES = b"OggS-voice"


def _voice_message(size: int | None = 1024) -> MagicMock:
    message = make_telegram_message()
    message.text = None
    message.caption = None
    message.bot.send_voice = AsyncMock()
    message.bot.send_chat_action = AsyncMock()
    message.voice = MagicMock()
    message.voice.file_size = size
    message.bot.download = AsyncMock(
        side_effect=lambda _file, destination=None: destination.write(_VOICE_BYTES)
    )
    return message


def _services(transcriber: MagicMock | None) -> BotServices:
    chat_client = AsyncMock()
    chat_client.process = AsyncMock(return_value=None)
    access_guard = AsyncMock()
    access_guard.ensure_access = AsyncMock(return_value=None)
    return BotServices(
        chat_client=chat_client,
        notes_client=AsyncMock(),
        access_guard=access_guard,
        texts=get_content().bot,
        speech_transcriber=transcriber,
        speech_enabled=True,
    )


def _transcriber(result: str | None) -> MagicMock:
    transcriber = MagicMock()
    transcriber.transcribe = AsyncMock(return_value=result)
    return transcriber


@pytest.mark.asyncio
async def test_transcript_becomes_a_text_turn() -> None:
    message = _voice_message()
    services = _services(_transcriber("  привет, как дела  "))
    await _handle_voice(services, message)

    services.speech_transcriber.transcribe.assert_awaited_once_with(
        _VOICE_BYTES, filename="voice.ogg"
    )
    incoming = services.chat_client.process.await_args.args[0]
    assert incoming.text == "  привет, как дела  "
    assert incoming.is_voice is True


@pytest.mark.asyncio
async def test_voice_is_ignored_without_a_transcriber() -> None:
    message = _voice_message()
    services = _services(None)
    await _handle_voice(services, message)
    message.bot.download.assert_not_awaited()
    services.chat_client.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_transcript_keeps_silence() -> None:
    message = _voice_message()
    services = _services(_transcriber(None))
    await _handle_voice(services, message)
    services.chat_client.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_transcription_errors_keep_silence() -> None:
    message = _voice_message()
    transcriber = _transcriber(None)
    transcriber.transcribe = AsyncMock(side_effect=RuntimeError("stt down"))
    services = _services(transcriber)
    await _handle_voice(services, message)
    services.chat_client.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_download_errors_keep_silence() -> None:
    message = _voice_message()
    message.bot.download = AsyncMock(side_effect=RuntimeError("network"))
    transcriber = _transcriber("привет")
    services = _services(transcriber)
    await _handle_voice(services, message)
    transcriber.transcribe.assert_not_awaited()
    services.chat_client.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_oversized_voice_is_skipped() -> None:
    message = _voice_message(size=64 * 1024 * 1024)
    transcriber = _transcriber("привет")
    services = _services(transcriber)
    await _handle_voice(services, message)
    message.bot.download.assert_not_awaited()
    transcriber.transcribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_download_keeps_silence() -> None:
    message = _voice_message()
    message.bot.download = AsyncMock(
        side_effect=lambda _file, destination=None: destination.write(b"")
    )
    services = _services(_transcriber("ага"))
    await _handle_voice(services, message)
    services.chat_client.process.assert_not_awaited()
