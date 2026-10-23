import asyncio
from unittest.mock import MagicMock

import fakeredis.aioredis
import pytest
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from services.bot.outbound import (
    OUTBOUND_GROUP,
    handle_outbound,
    run_outbound_loop,
    start_outbound_task,
)
from vanessa.contracts import OutboundMessage, TurnRequest
from vanessa.infrastructure.broker.backends import Delivery
from vanessa.infrastructure.broker.redis_streams import RedisStreamBroker
from vanessa.infrastructure.broker.streams import BrokerStreams

CHAT_ID = -100
STREAM = "vanessa:outbound"
REPLY_TO = 77
TWO_ATTEMPTS = 2


class FakeBot:
    """Records ``send_message`` calls; ``fail`` decides which calls raise."""

    def __init__(self, fail=None) -> None:
        self.calls: list[dict] = []
        self._fail = fail or (lambda _call: None)

    async def send_message(self, chat_id, text, **kwargs) -> None:
        call = {"chat_id": chat_id, "text": text, **kwargs}
        self.calls.append(call)
        error = self._fail(call)
        if error is not None:
            raise error


def _outbound(**overrides) -> OutboundMessage:
    fields = {
        "telegram_chat_id": CHAT_ID,
        "text": "**done**",
        "reply_to_message_id": REPLY_TO,
        "source": "hermes",
    }
    return OutboundMessage(**{**fields, **overrides})


def _delivery(message) -> Delivery:
    return Delivery(stream=STREAM, stream_id="1-0", message=message)


def _bad_request(text: str = "bad") -> TelegramBadRequest:
    return TelegramBadRequest(MagicMock(), text)


async def test_posts_html_reply_to_original_message() -> None:
    bot = FakeBot()
    await handle_outbound(bot, _delivery(_outbound()))
    assert len(bot.calls) == 1
    call = bot.calls[0]
    assert call["chat_id"] == CHAT_ID
    assert call["text"] == "<b>done</b>"
    assert call["parse_mode"] == ParseMode.HTML
    assert call["reply_parameters"].message_id == REPLY_TO
    assert call["reply_parameters"].allow_sending_without_reply is True


async def test_posts_without_reply_when_no_target() -> None:
    bot = FakeBot()
    await handle_outbound(bot, _delivery(_outbound(reply_to_message_id=None)))
    assert len(bot.calls) == 1
    assert "reply_parameters" not in bot.calls[0]


async def test_falls_back_to_plain_message_when_reply_target_rejected() -> None:
    def fail(call):
        if "reply_parameters" in call:
            return _bad_request("message to be replied not found")
        return None

    bot = FakeBot(fail=fail)
    await handle_outbound(bot, _delivery(_outbound()))
    with_reply = [c for c in bot.calls if "reply_parameters" in c]
    without_reply = [c for c in bot.calls if "reply_parameters" not in c]
    assert len(with_reply) == TWO_ATTEMPTS  # HTML, then plain text
    assert len(without_reply) == 1
    assert without_reply[0]["text"] == "<b>done</b>"


@pytest.mark.parametrize(
    ("message", "allowed"),
    [
        (_outbound(channel="vrchat"), 0),
        (_outbound(telegram_chat_id=-200), CHAT_ID),
        (TurnRequest(correlation_id="c", telegram_chat_id=1, message="x", sender_telegram_id=2), 0),
    ],
)
async def test_skips_other_channel_wrong_chat_and_other_kinds(message, allowed) -> None:
    bot = FakeBot()
    await handle_outbound(bot, _delivery(message), allowed_chat_id=allowed)
    assert bot.calls == []


async def test_allowed_chat_matches_posts() -> None:
    bot = FakeBot()
    await handle_outbound(bot, _delivery(_outbound()), allowed_chat_id=CHAT_ID)
    assert len(bot.calls) == 1


async def test_send_error_is_swallowed() -> None:
    bot = FakeBot(fail=lambda _call: TelegramNetworkError(MagicMock(), "down"))
    await handle_outbound(bot, _delivery(_outbound()))
    assert len(bot.calls) == TWO_ATTEMPTS  # with reply, then without reply


async def test_unexpected_error_is_swallowed(monkeypatch) -> None:
    async def boom(_bot, _message):
        raise RuntimeError("boom")

    monkeypatch.setattr("services.bot.outbound.consumer.post_outbound", boom)
    await handle_outbound(FakeBot(), _delivery(_outbound()))


@pytest.fixture
def redis_client():
    return fakeredis.aioredis.FakeRedis()


async def _run_loop_once(redis_client, bot, message) -> None:
    broker = RedisStreamBroker("redis://unused", client=redis_client)
    task = asyncio.create_task(run_outbound_loop(broker, bot, stream=STREAM, consumer="c1"))
    await asyncio.sleep(0.05)
    await broker.publish(STREAM, message)
    await asyncio.sleep(0.2)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_loop_posts_and_acks(redis_client) -> None:
    bot = FakeBot()
    await _run_loop_once(redis_client, bot, _outbound(text="hi"))
    assert [c["text"] for c in bot.calls] == ["hi"]
    pending = await redis_client.xpending(STREAM, OUTBOUND_GROUP)
    assert pending["pending"] == 0


async def test_loop_survives_send_error_and_acks_without_dlq(redis_client) -> None:
    bot = FakeBot(fail=lambda _call: TelegramNetworkError(MagicMock(), "down"))
    await _run_loop_once(redis_client, bot, _outbound(text="hi"))
    assert bot.calls
    pending = await redis_client.xpending(STREAM, OUTBOUND_GROUP)
    assert pending["pending"] == 0
    assert await redis_client.xlen(f"{STREAM}:dlq") == 0


async def test_loop_restarts_after_broker_failure() -> None:
    broker = MagicMock()
    calls: list[int] = []

    async def consume_forever(*_args, **_kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("redis down")
        await asyncio.Event().wait()

    broker.consume_forever = consume_forever
    task = asyncio.create_task(
        run_outbound_loop(broker, FakeBot(), stream=STREAM, consumer="c1", retry_seconds=0)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert len(calls) == TWO_ATTEMPTS


async def test_start_outbound_task_needs_broker_and_stream() -> None:
    streams = BrokerStreams(prefix="v", turns="v:turns", tasks="v:tasks")
    assert start_outbound_task(None, streams, FakeBot()) is None
    assert start_outbound_task(MagicMock(), streams, FakeBot()) is None


async def test_start_outbound_task_runs_loop(redis_client) -> None:
    broker = RedisStreamBroker("redis://unused", client=redis_client)
    streams = BrokerStreams(prefix="v", turns="v:turns", tasks="v:tasks", outbound=STREAM)
    bot = FakeBot()
    task = start_outbound_task(broker, streams, bot)
    assert task is not None
    await asyncio.sleep(0.05)
    await broker.publish(STREAM, _outbound(text="late"))
    await asyncio.sleep(0.2)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert [c["text"] for c in bot.calls] == ["late"]
