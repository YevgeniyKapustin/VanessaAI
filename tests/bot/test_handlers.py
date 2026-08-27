import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest

from app.bot.container import BotServices, create_bot_services
from app.bot.handlers.messages import (
    _preview,
    _send_reply,
    _typing_loop,
    _typing_on_signal,
    create_messages_router,
)
from app.bot.messages.response import ChatProcessResult
from app.config.content import get_content
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


def _services(
    *,
    access_error: str | None = None,
    api_result: ChatProcessResult | None = None,
    api_error: Exception | None = None,
    stickers=None,
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
    )


async def _call_text_handler(services: BotServices, message: MagicMock) -> None:
    router = create_messages_router(services)
    handler = router.message.handlers[-1].callback
    await handler(message)


async def _call_start_handler(services: BotServices, message: MagicMock) -> None:
    router = create_messages_router(services)
    handler = router.message.handlers[0].callback
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
