"""Inbound stickers and GIFs: the vision turn the bot builds from a thumbnail."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.bot.container import BotServices
from services.bot.handlers.messages import create_messages_router
from services.bot.messages.response import ChatProcessResult
from tests.bot.test_bot_message import make_telegram_message
from vanessa.config.content import (
    get_content,
    get_gif_placeholder,
    get_sticker_placeholder,
)
from vanessa.config.settings import settings
from vanessa.core.messages_attachments import KIND_GIF, KIND_STICKER

JPEG_BYTES = b"fakejpegbytes"


def _services(api_result: ChatProcessResult | None = None) -> BotServices:
    chat_client = AsyncMock()
    chat_client.process = AsyncMock(
        return_value=api_result
        or ChatProcessResult(action="ignore", reason="ignore", relevance_score=0.0)
    )
    access_guard = AsyncMock()
    access_guard.ensure_access = AsyncMock(return_value=None)
    access_guard.is_private_chat = MagicMock(return_value=True)
    return BotServices(
        chat_client=chat_client,
        notes_client=AsyncMock(),
        access_guard=access_guard,
        texts=get_content().bot,
    )


def _handler(services: BotServices, name: str):
    router = create_messages_router(services)
    for handler in router.message.handlers:
        if getattr(handler.callback, "__name__", "") == name:
            return handler.callback
    raise AssertionError(f"handler '{name}' not found")


def _downloader():
    return AsyncMock(
        side_effect=lambda _file, destination=None: destination.write(JPEG_BYTES)
    )


def _sticker_message(emoji: str | None = "😀", *, thumbnail: MagicMock | None = None):
    message = make_telegram_message()
    message.text = None
    message.caption = None
    sticker = MagicMock()
    sticker.emoji = emoji
    sticker.set_name = "VanessaBot"
    sticker.thumbnail = (
        thumbnail if thumbnail is not None else MagicMock(file_id="thumb", file_size=1000)
    )
    message.sticker = sticker
    message.animation = None
    message.bot.download = _downloader()
    message.reply = AsyncMock()
    return message


def _animation_message(*, caption: str | None, thumbnail: MagicMock | None = None):
    message = make_telegram_message()
    message.text = None
    message.caption = caption
    message.sticker = None
    animation = MagicMock()
    animation.thumbnail = (
        thumbnail if thumbnail is not None else MagicMock(file_id="gifthumb", file_size=900)
    )
    message.animation = animation
    message.bot.download = _downloader()
    message.reply = AsyncMock()
    return message


@pytest.mark.asyncio
async def test_sticker_is_sent_to_vision_as_a_sticker_image():
    message = _sticker_message("😀")
    services = _services()

    await _handler(services, "handle_sticker")(message)

    incoming = services.chat_client.process.await_args.args[0]
    assert incoming.text == f"{get_sticker_placeholder()} 😀"
    assert len(incoming.images) == 1
    assert incoming.images[0].kind == KIND_STICKER
    assert incoming.images[0].data_url.startswith("data:image/jpeg;base64,")
    assert incoming.images[0].telegram_file_id == "thumb"


@pytest.mark.asyncio
async def test_sticker_without_emoji_keeps_the_bare_placeholder():
    message = _sticker_message(None)
    services = _services()

    await _handler(services, "handle_sticker")(message)

    incoming = services.chat_client.process.await_args.args[0]
    assert incoming.text == get_sticker_placeholder()


@pytest.mark.asyncio
async def test_sticker_without_thumbnail_is_ignored():
    message = _sticker_message("😀", thumbnail=MagicMock(spec=[]))
    message.sticker.thumbnail = None
    services = _services()

    await _handler(services, "handle_sticker")(message)

    services.chat_client.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_sticker_download_failure_is_swallowed():
    message = _sticker_message("😀")
    message.bot.download = AsyncMock(side_effect=RuntimeError("telegram down"))
    services = _services()

    await _handler(services, "handle_sticker")(message)

    services.chat_client.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_gif_uses_its_caption_and_a_gif_preview_frame():
    message = _animation_message(caption="смотри что поймал")
    services = _services()

    await _handler(services, "handle_animation")(message)

    incoming = services.chat_client.process.await_args.args[0]
    assert incoming.text == "смотри что поймал"
    assert incoming.images[0].kind == KIND_GIF


@pytest.mark.asyncio
async def test_gif_without_caption_uses_the_placeholder():
    message = _animation_message(caption=None)
    services = _services()

    await _handler(services, "handle_animation")(message)

    incoming = services.chat_client.process.await_args.args[0]
    assert incoming.text == get_gif_placeholder()


@pytest.mark.asyncio
async def test_gif_without_preview_and_caption_is_dropped():
    message = _animation_message(caption=None)
    message.animation.thumbnail = None
    services = _services()

    await _handler(services, "handle_animation")(message)

    services.chat_client.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_sticker_is_ignored_when_vision_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "vision_enabled", False)
    message = _sticker_message("😀")
    services = _services()

    await _handler(services, "handle_sticker")(message)

    services.chat_client.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_gif_with_caption_still_reaches_the_pipeline_without_vision(monkeypatch):
    monkeypatch.setattr(settings, "vision_enabled", False)
    message = _animation_message(caption="голый текст")
    services = _services()

    await _handler(services, "handle_animation")(message)

    incoming = services.chat_client.process.await_args.args[0]
    assert incoming.text == "голый текст"
    assert incoming.images == ()
