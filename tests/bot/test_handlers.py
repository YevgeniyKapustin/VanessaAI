import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest

from app.bot.container import BotServices, create_bot_services
from app.bot.handlers.messages import (
    _pick_photo_size,
    _preview,
    _send_photo,
    _send_reply,
    _send_reply_messages,
    _typing_loop,
    _typing_on_signal,
    create_messages_router,
)
from app.bot.messages.response import ChatProcessResult
from app.config.content import get_content
from app.config.settings import settings
from tests.bot.test_bot_message import make_telegram_message


@pytest.mark.asyncio
async def test_preview_truncates_long_text():
    text = "a" * 120
    assert _preview(text).endswith("...")
    assert len(_preview(text)) <= 83


def test_create_bot_services_wires_dependencies():
    services = create_bot_services()
    assert services.chat_client is not None
    assert services.access_guard is not None
    assert services.texts.welcome == get_content().bot.welcome


@pytest.mark.asyncio
async def test_send_reply_falls_back_on_bad_html():
    message = make_telegram_message()
    message.reply = AsyncMock(
        side_effect=[TelegramBadRequest(MagicMock(), "bad"), None]
    )
    await _send_reply(message, "plain text")
    assert message.reply.await_count == 2
    second_call = message.reply.await_args_list[1]
    assert second_call.args[0] == "plain text"


@pytest.mark.asyncio
async def test_send_reply_uses_html_parse_mode():
    message = make_telegram_message()
    message.reply = AsyncMock()
    await _send_reply(message, "code `x`")
    message.reply.assert_awaited_once()
    assert message.reply.await_args.kwargs["parse_mode"] == ParseMode.HTML


@pytest.mark.asyncio
async def test_send_reply_messages_first_replies_rest_answer():
    message = make_telegram_message()
    message.reply = AsyncMock()
    message.answer = AsyncMock()
    await _send_reply_messages(message, ["Один", "Два", "Три"], delay=0.0)
    assert message.reply.await_count == 1
    assert message.answer.await_count == 2
    # only the first block is sent as a reply to the user's message
    assert message.reply.await_args.args[0] is not None
    assert message.answer.await_args.args[0] is not None


@pytest.mark.asyncio
async def test_send_reply_messages_stops_on_hard_error():
    message = make_telegram_message()
    message.reply = AsyncMock(side_effect=RuntimeError("flood"))
    message.answer = AsyncMock()
    await _send_reply_messages(message, ["Один", "Два"], delay=0.0)
    # a hard failure stops the loop — no hammering the unreachable chat
    message.reply.assert_awaited_once()
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_reply_messages_falls_back_to_plain_text():
    message = make_telegram_message()
    message.reply = AsyncMock(
        side_effect=[TelegramBadRequest(MagicMock(), "bad"), None]
    )
    message.answer = AsyncMock()
    await _send_reply_messages(message, ["Один"], delay=0.0)
    assert message.reply.await_count == 2
    assert message.reply.await_args_list[1].args[0] == "Один"


def _services(
    *,
    access_error: str | None = None,
    api_result: ChatProcessResult | None = None,
    api_error: Exception | None = None,
    stickers=None,
    message_delay_seconds: float = 0.7,
    max_messages: int = 8,
) -> BotServices:
    chat_client = AsyncMock()
    if api_error is not None:
        chat_client.process = AsyncMock(side_effect=api_error)
    else:
        result = api_result or ChatProcessResult(
            action="ignore",
            reason="ignore",
            reply=None,
            relevance_score=0.0,
        )

        async def _process(message, on_started=None):
            # Simulate the API SSE stream: the "started" event is emitted only
            # when the decision gate passes and Vanessa commits to an actual
            # reply — never for ignored messages.
            if result.action == "reply" and on_started is not None:
                await on_started()
            return result

        chat_client.process = AsyncMock(side_effect=_process)
    access_guard = AsyncMock()
    access_guard.ensure_access = AsyncMock(return_value=access_error)
    knowledge = AsyncMock()
    knowledge.is_configured = False
    return BotServices(
        chat_client=chat_client,
        access_guard=access_guard,
        knowledge=knowledge,
        texts=get_content().bot,
        stickers=stickers,
        message_delay_seconds=message_delay_seconds,
        max_messages=max_messages,
    )


def _find_handler(router, name: str):
    for handler in router.message.handlers:
        if getattr(handler.callback, "__name__", "") == name:
            return handler.callback
    raise AssertionError(f"handler '{name}' not found")


async def _call_text_handler(services: BotServices, message: MagicMock) -> None:
    router = create_messages_router(services)
    handler = _find_handler(router, "handle_text")
    await handler(message)


async def _call_start_handler(services: BotServices, message: MagicMock) -> None:
    router = create_messages_router(services)
    handler = _find_handler(router, "cmd_start")
    await handler(message)


async def _call_photo_handler(services: BotServices, message: MagicMock) -> None:
    router = create_messages_router(services)
    handler = _find_handler(router, "handle_photo")
    await handler(message)


@pytest.mark.asyncio
async def test_handle_text_ignores_when_access_denied():
    message = make_telegram_message()
    message.answer = AsyncMock()
    services = _services(access_error="no access")
    await _call_text_handler(services, message)
    message.answer.assert_awaited_once_with("no access")
    services.chat_client.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_text_swallows_api_error():
    message = make_telegram_message()
    message.reply = AsyncMock()
    services = _services(api_error=httpx.ConnectError("down"))
    await _call_text_handler(services, message)
    message.reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_text_sends_reply():
    message = make_telegram_message(text="Vanessa?")
    message.reply = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Да?",
            relevance_score=0.9,
        )
    )
    await _call_text_handler(services, message)
    # typing is shown while the pipeline runs (initial ping, plus refreshes)
    assert message.bot.send_chat_action.await_count >= 1
    message.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_text_sends_multiple_reply_messages():
    message = make_telegram_message(text="Vanessa?")
    message.reply = AsyncMock()
    message.answer = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Первая мысль\nВторая мысль",
            messages=["Первая мысль", "Вторая мысль"],
            relevance_score=0.9,
        ),
        message_delay_seconds=0.0,
    )
    await _call_text_handler(services, message)
    # the first block is a reply to the user, the rest are plain messages
    message.reply.assert_awaited_once()
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_text_caps_reply_messages():
    message = make_telegram_message(text="Vanessa?")
    message.reply = AsyncMock()
    message.answer = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="1\n2\n3",
            messages=["1", "2", "3"],
            relevance_score=0.9,
        ),
        message_delay_seconds=0.0,
        max_messages=1,
    )
    await _call_text_handler(services, message)
    # the safety cap stops flooding: only the first block is delivered
    message.reply.assert_awaited_once()
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_text_ignores_non_reply():
    message = make_telegram_message(text="просто болтовня")
    message.answer = AsyncMock()
    message.reply = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="ignore",
            reason="noise",
            reply=None,
            relevance_score=0.1,
        )
    )
    await _call_text_handler(services, message)
    message.answer.assert_not_awaited()
    message.reply.assert_not_awaited()
    # No "typing..." at all: the gate ignored the message, so Vanessa never
    # pretended she started writing.
    assert message.bot.send_chat_action.await_count == 0


@pytest.mark.asyncio
async def test_cmd_start_sends_welcome():
    message = make_telegram_message(text="/start")
    message.answer = AsyncMock()
    services = _services()
    await _call_start_handler(services, message)
    message.answer.assert_awaited_once()
    assert services.texts.welcome.strip() in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_handle_text_sends_sticker_when_tagged():
    message = make_telegram_message(text="Vanessa?")
    message.reply = AsyncMock()
    sticker_service = AsyncMock()
    sticker_service.register_reply = MagicMock()
    sticker_service.is_sticker_only = MagicMock(return_value=False)
    sticker_service.send_if_any = AsyncMock(return_value="sarcasm")
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Да?",
            relevance_score=0.9,
            sticker_tag="sarcasm",
        ),
        stickers=sticker_service,
    )
    await _call_text_handler(services, message)
    message.reply.assert_awaited_once()
    sticker_service.register_reply.assert_called_once_with(-100123)
    sticker_service.send_if_any.assert_awaited_once()
    assert sticker_service.send_if_any.await_args.args[0] is message
    kwargs = sticker_service.send_if_any.await_args.kwargs
    assert kwargs["sticker_tag"] == "sarcasm"
    assert kwargs["reply_text"] == "Да?"
    assert kwargs["force"] is False


@pytest.mark.asyncio
async def test_handle_text_forces_sticker_on_explicit_request():
    message = make_telegram_message(text="ванесса кинь стикер")
    message.reply = AsyncMock()
    sticker_service = AsyncMock()
    sticker_service.register_reply = MagicMock()
    sticker_service.is_sticker_only = MagicMock(return_value=False)
    sticker_service.send_if_any = AsyncMock(return_value="delight")
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Держи",
            relevance_score=0.9,
            sticker_tag="delight",
        ),
        stickers=sticker_service,
    )
    await _call_text_handler(services, message)
    message.reply.assert_awaited_once()
    sticker_service.send_if_any.assert_awaited_once()
    kwargs = sticker_service.send_if_any.await_args.kwargs
    assert kwargs["force"] is True


@pytest.mark.asyncio
async def test_handle_text_sticker_only_suppresses_text():
    message = make_telegram_message(text="что?")
    message.reply = AsyncMock()
    sticker_service = AsyncMock()
    sticker_service.register_reply = MagicMock()
    sticker_service.is_sticker_only = MagicMock(return_value=True)
    sticker_service.send_if_any = AsyncMock(return_value="bemused")
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Серьёзно?",
            relevance_score=0.9,
            sticker_tag="bemused",
        ),
        stickers=sticker_service,
    )
    await _call_text_handler(services, message)
    # the sticker itself is the whole reply — no text (typing still shows while
    # the pipeline runs)
    message.reply.assert_not_awaited()
    assert message.bot.send_chat_action.await_count >= 1
    sticker_service.register_reply.assert_called_once_with(-100123)
    sticker_service.send_if_any.assert_awaited_once()
    kwargs = sticker_service.send_if_any.await_args.kwargs
    assert kwargs["sticker_tag"] == "bemused"
    assert kwargs["reply_text"] is None
    assert kwargs["force"] is True


@pytest.mark.asyncio
async def test_handle_text_sticker_only_falls_back_to_text():
    message = make_telegram_message(text="что?")
    message.reply = AsyncMock()
    sticker_service = AsyncMock()
    sticker_service.register_reply = MagicMock()
    sticker_service.is_sticker_only = MagicMock(return_value=True)
    sticker_service.send_if_any = AsyncMock(return_value=None)
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Серьёзно?",
            relevance_score=0.9,
            sticker_tag="bemused",
        ),
        stickers=sticker_service,
    )
    await _call_text_handler(services, message)
    # sticker couldn't be sent — fall back to the text answer
    message.reply.assert_awaited_once()
    sticker_service.send_if_any.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_text_sticker_only_empty_reply_sends_sticker():
    # The model answered with ONLY a sticker marker (e.g. [sticker:bemused]):
    # the pipeline strips the marker, so reply is "" but sticker_tag is set.
    # This must NOT be treated as an ignored message — the sticker IS the reply
    # and has to be delivered even though there is no accompanying text.
    message = make_telegram_message(text="что?")
    message.reply = AsyncMock()
    sticker_service = AsyncMock()
    sticker_service.register_reply = MagicMock()
    sticker_service.is_sticker_only = MagicMock(return_value=True)
    sticker_service.send_if_any = AsyncMock(return_value="bemused")
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="",
            messages=[],
            relevance_score=0.9,
            sticker_tag="bemused",
        ),
        stickers=sticker_service,
    )
    await _call_text_handler(services, message)
    # the sticker is delivered, no (empty) text is sent
    message.reply.assert_not_awaited()
    sticker_service.register_reply.assert_called_once_with(-100123)
    sticker_service.send_if_any.assert_awaited_once()
    kwargs = sticker_service.send_if_any.await_args.kwargs
    assert kwargs["sticker_tag"] == "bemused"
    assert kwargs["reply_text"] is None
    assert kwargs["force"] is True


@pytest.mark.asyncio
async def test_handle_text_sticker_only_empty_reply_no_text_fallback():
    # Same marker-only answer, but the sticker could not be delivered: with no
    # text answer to fall back on, the handler sends nothing instead of an empty
    # message — the failure is logged, the turn never crashes.
    message = make_telegram_message(text="что?")
    message.reply = AsyncMock()
    sticker_service = AsyncMock()
    sticker_service.register_reply = MagicMock()
    sticker_service.is_sticker_only = MagicMock(return_value=True)
    sticker_service.send_if_any = AsyncMock(return_value=None)
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="",
            messages=[],
            relevance_score=0.9,
            sticker_tag="bemused",
        ),
        stickers=sticker_service,
    )
    await _call_text_handler(services, message)
    # nothing is sent (no empty message) and the sticker was attempted
    message.reply.assert_not_awaited()
    sticker_service.send_if_any.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_text_no_sticker_when_service_absent():
    message = make_telegram_message(text="Vanessa?")
    message.reply = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Да?",
            relevance_score=0.9,
            sticker_tag="sarcasm",
        ),
        stickers=None,
    )
    await _call_text_handler(services, message)
    message.reply.assert_awaited_once()


def test_create_router_includes_messages():
    from app.bot.handlers import create_router

    router = create_router(create_bot_services())
    assert router.sub_routers


@pytest.mark.asyncio
async def test_typing_loop_refreshes_until_cancelled():
    bot = MagicMock()
    bot.send_chat_action = AsyncMock()
    task = asyncio.create_task(_typing_loop(bot, -100123, interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert bot.send_chat_action.await_count >= 2


@pytest.mark.asyncio
async def test_typing_loop_survives_telegram_errors():
    bot = MagicMock()
    bot.send_chat_action = AsyncMock(side_effect=RuntimeError("chat not found"))
    # Telegram-side failures must not kill the indicator for the whole turn:
    # the loop keeps trying until cancelled and never propagates the error.
    task = asyncio.create_task(_typing_loop(bot, -100123, interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert bot.send_chat_action.await_count >= 2


@pytest.mark.asyncio
async def test_typing_loop_recovers_after_transient_error():
    bot = MagicMock()
    bot.send_chat_action = AsyncMock(side_effect=[RuntimeError("boom"), None])
    # The first ping fails but the loop must keep going and send the next one.
    task = asyncio.create_task(_typing_loop(bot, -100123, interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert bot.send_chat_action.await_count >= 2


@pytest.mark.asyncio
async def test_typing_on_signal_cancels_on_error():
    bot = MagicMock()
    bot.send_chat_action = AsyncMock()
    with pytest.raises(RuntimeError):
        async with _typing_on_signal(bot, -100123) as start_typing:
            await start_typing()
            raise RuntimeError("boom")
    # The trigger was fired so the first ping was sent, then the block error
    # propagated and the refresh loop was cancelled on exit.
    assert bot.send_chat_action.await_count >= 1


@pytest.mark.asyncio
async def test_typing_on_signal_stays_silent_until_triggered():
    bot = MagicMock()
    bot.send_chat_action = AsyncMock()
    async with _typing_on_signal(bot, -100123):
        # The trigger was never fired — no "typing..." should be sent at all.
        await asyncio.sleep(0)
    assert bot.send_chat_action.await_count == 0


@pytest.mark.asyncio
async def test_handle_text_typing_shown_while_request_pending():
    message = make_telegram_message(text="Vanessa?")
    message.reply = AsyncMock()
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_process(incoming, on_started=None):
        started.set()
        # The API emits "started" once the gate passes, while the pipeline is
        # still composing the answer.
        if on_started is not None:
            await on_started()
        await release.wait()
        return ChatProcessResult(
            action="reply", reason="intent", reply="Да?", relevance_score=0.9
        )

    services = _services()
    services.chat_client.process = AsyncMock(side_effect=slow_process)

    handler_task = asyncio.create_task(_call_text_handler(services, message))
    await started.wait()
    # Give the typing loop a chance to run its first iteration.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert message.bot.send_chat_action.await_count >= 1
    release.set()
    await handler_task
    message.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_text_no_typing_before_access_check():
    message = make_telegram_message(text="Vanessa?")
    message.answer = AsyncMock()
    message.reply = AsyncMock()
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_access(incoming):
        started.set()
        await release.wait()
        return None

    services = _services()
    services.access_guard.ensure_access = AsyncMock(side_effect=slow_access)

    handler_task = asyncio.create_task(_call_text_handler(services, message))
    await started.wait()
    # Give the access guard a chance to run while it is still blocked.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # typing must NOT appear while the access guard is running — the indicator
    # only starts once the API signals that the gate passed.
    assert message.bot.send_chat_action.await_count == 0
    release.set()
    await handler_task


@pytest.mark.asyncio
async def test_handle_text_pings_typing_again_before_reply():
    message = make_telegram_message(text="Vanessa?")
    message.reply = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Привет!",
            relevance_score=0.9,
        )
    )
    await _call_text_handler(services, message)
    message.reply.assert_awaited_once()
    # typing is refreshed right before the reply is delivered (start ping plus
    # the pre-reply ping), so the indicator never dies in the tail of the
    # pipeline.
    assert message.bot.send_chat_action.await_count >= 2


def test_pick_photo_size_prefers_largest_within_cap():
    small = MagicMock(file_id="small", file_size=1000)
    medium = MagicMock(file_id="medium", file_size=50000)
    huge = MagicMock(file_id="huge", file_size=10_000_000)
    chosen = _pick_photo_size([small, medium, huge], max_bytes=1_500_000)
    assert chosen.file_id == "medium"


def test_pick_photo_size_falls_back_to_smallest_when_all_exceed_cap():
    big = MagicMock(file_id="big", file_size=2_000_000)
    bigger = MagicMock(file_id="bigger", file_size=5_000_000)
    chosen = _pick_photo_size([big, bigger], max_bytes=1_000_000)
    assert chosen.file_id == "big"


def test_pick_photo_size_empty_returns_none():
    assert _pick_photo_size([], max_bytes=1_500_000) is None


@pytest.mark.asyncio
async def test_handle_photo_downloads_and_sends_image_to_api():
    message = make_telegram_message()
    message.text = None
    message.caption = None
    message.photo = [
        MagicMock(file_id="small", file_size=1000),
        MagicMock(file_id="large", file_size=50_000),
    ]
    message.bot.download = AsyncMock(
        side_effect=lambda photo, destination=None: destination.write(b"fakejpegbytes")
    )
    message.reply = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="На фото кот",
            relevance_score=0.9,
        )
    )

    await _call_photo_handler(services, message)

    # The API received a bare photo as the placeholder text + one base64 image.
    call = services.chat_client.process.await_args
    incoming = call.args[0]
    assert incoming.text == settings.vision_photo_placeholder
    assert len(incoming.images) == 1
    assert incoming.images[0].data_url.startswith("data:image/jpeg;base64,")
    assert incoming.images[0].telegram_file_id == "large"
    message.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_photo_uses_caption_as_text():
    message = make_telegram_message()
    message.text = None
    message.caption = "смотри что за зверь"
    message.photo = [MagicMock(file_id="p1", file_size=1000)]
    message.bot.download = AsyncMock(
        side_effect=lambda photo, destination=None: destination.write(b"fakejpegbytes")
    )
    message.reply = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Это же крабер",
            relevance_score=0.9,
        )
    )

    await _call_photo_handler(services, message)

    call = services.chat_client.process.await_args
    incoming = call.args[0]
    assert incoming.text == "смотри что за зверь"
    assert len(incoming.images) == 1


@pytest.mark.asyncio
async def test_handle_photo_vision_disabled_drops_bare_photo(monkeypatch):
    monkeypatch.setattr(settings, "vision_enabled", False)
    message = make_telegram_message()
    message.text = None
    message.caption = None
    message.photo = [MagicMock(file_id="p1", file_size=1000)]
    message.bot.download = AsyncMock()
    message.reply = AsyncMock()
    services = _services()

    await _call_photo_handler(services, message)

    services.chat_client.process.assert_not_awaited()
    message.reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_photo_vision_disabled_uses_caption_text(monkeypatch):
    monkeypatch.setattr(settings, "vision_enabled", False)
    message = make_telegram_message()
    message.text = None
    message.caption = "голый текст"
    message.photo = [MagicMock(file_id="p1", file_size=1000)]
    message.reply = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Понял",
            relevance_score=0.9,
        )
    )

    await _call_photo_handler(services, message)

    call = services.chat_client.process.await_args
    incoming = call.args[0]
    assert incoming.text == "голый текст"
    assert incoming.images == ()
    message.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_text_sends_photo_when_requested():
    message = make_telegram_message(text="скинь фото с котом")
    message.reply = AsyncMock()
    message.bot.send_photo = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Держи",
            relevance_score=0.9,
            photo_file_id="file-1",
        )
    )

    await _call_text_handler(services, message)

    message.reply.assert_awaited_once()
    message.bot.send_photo.assert_awaited_once_with(-100123, photo="file-1")


@pytest.mark.asyncio
async def test_handle_text_no_photo_without_photo_file_id():
    message = make_telegram_message(text="скинь фото с котом")
    message.reply = AsyncMock()
    message.bot.send_photo = AsyncMock()
    services = _services(
        api_result=ChatProcessResult(
            action="reply",
            reason="intent",
            reply="Нет фото",
            relevance_score=0.9,
        )
    )

    await _call_text_handler(services, message)

    message.reply.assert_awaited_once()
    message.bot.send_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_photo_success_by_file_id():
    message = make_telegram_message()
    message.bot.send_photo = AsyncMock()
    sent = await _send_photo(message, "file-1")
    assert sent is True
    message.bot.send_photo.assert_awaited_once()
    message.reply.assert_not_called()


@pytest.mark.asyncio
async def test_send_photo_falls_back_to_upload_from_data_url():
    """A stale Telegram file_id must not lose the photo: fall back to uploading
    the stored bytes (data_url) instead of silently leaving a fake 'sent'."""
    message = make_telegram_message()
    message.bot.send_photo = AsyncMock(
        side_effect=[RuntimeError("stale file_id"), None]
    )
    sent = await _send_photo(
        message,
        "file-1",
        data_url="data:image/jpeg;base64,aGVsbG8=",  # base64("hello")
    )
    assert sent is True
    assert message.bot.send_photo.await_count == 2
    # The second call re-uploads the decoded bytes, not the stale file_id.
    second_args = message.bot.send_photo.await_args_list[1]
    assert second_args.kwargs["photo"] is not None
    message.reply.assert_not_called()


@pytest.mark.asyncio
async def test_send_photo_sends_text_fallback_when_no_data_url():
    """No stored bytes available and the file_id fails: tell the user plainly
    instead of leaving them believing a photo was sent."""
    message = make_telegram_message()
    message.bot.send_photo = AsyncMock(side_effect=RuntimeError("cannot resend"))
    message.reply = AsyncMock()
    sent = await _send_photo(message, "file-1")
    assert sent is False
    message.bot.send_photo.assert_awaited_once()
    message.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_photo_sends_text_fallback_when_upload_also_fails():
    message = make_telegram_message()
    message.bot.send_photo = AsyncMock(
        side_effect=[RuntimeError("stale file_id"), RuntimeError("upload failed")]
    )
    message.reply = AsyncMock()
    sent = await _send_photo(
        message,
        "file-1",
        data_url="data:image/jpeg;base64,aGVsbG8=",
    )
    assert sent is False
    assert message.bot.send_photo.await_count == 2
    message.reply.assert_awaited_once()
