import asyncio

import fakeredis.aioredis
import pytest
from aiogram import Bot

from services.bot.messages import IncomingMessage
from services.bot.services.broker_client import BrokerTurnClient
from vanessa.contracts.messages import TurnReply, TurnStarted
from vanessa.infrastructure.broker.backends import Delivery
from vanessa.infrastructure.broker.redis_streams import RedisStreamBroker
from vanessa.infrastructure.broker.streams import BrokerStreams


@pytest.fixture
def broker():
    client = fakeredis.aioredis.FakeRedis()
    return RedisStreamBroker("redis://localhost:6379/0", client=client)


def _incoming(chat_id: int = 1, message_id: int = 7) -> IncomingMessage:
    return IncomingMessage(
        telegram_chat_id=chat_id,
        telegram_message_id=message_id,
        text="hello",
        sender_telegram_id=2,
        chat_type="group",
        bot=Bot(token="123456:TEST"),
    )


async def test_client_process_roundtrip(broker) -> None:
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")
    client = BrokerTurnClient(
        broker, streams=streams, timeout=3.0, bot_id="bot-1"
    )

    async def agent_side(delivery: Delivery) -> None:
        req = delivery.message
        await broker.publish(
            req.reply_to,
            TurnStarted(correlation_id=req.correlation_id),
        )
        await broker.publish(
            req.reply_to,
            TurnReply(
                correlation_id=req.correlation_id,
                action="reply",
                reason="intent",
                reply="pong",
                messages=["pong"],
                relevance_score=0.9,
            ),
        )

    agent_task = asyncio.create_task(
        broker.consume_forever(
            streams.turns, "agent-core", "w1", agent_side, poll_seconds=0.01
        )
    )
    await asyncio.sleep(0.05)

    started_calls: list[str] = []

    async def on_started() -> None:
        started_calls.append("started")

    result = await client.process(_incoming(), on_started=on_started)
    agent_task.cancel()
    await asyncio.gather(agent_task, return_exceptions=True)

    assert started_calls == ["started"]
    assert result.action == "reply"
    assert result.reason == "intent"
    assert result.reply == "pong"
    assert result.messages == ["pong"]
    assert result.relevance_score == 0.9


async def test_client_uses_correlation_id_from_message(broker) -> None:
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")
    client = BrokerTurnClient(broker, streams=streams, timeout=3.0, bot_id="bot-2")

    captured: list[str] = []

    async def agent_side(delivery: Delivery) -> None:
        req = delivery.message
        captured.append(req.correlation_id)
        await broker.publish(
            req.reply_to,
            TurnReply(correlation_id=req.correlation_id, action="ignore", reason="noise"),
        )

    agent_task = asyncio.create_task(
        broker.consume_forever(
            streams.turns, "agent-core", "w1", agent_side, poll_seconds=0.01
        )
    )
    await asyncio.sleep(0.05)
    incoming = _incoming(chat_id=42, message_id=99)
    result = await client.process(incoming)
    agent_task.cancel()
    await asyncio.gather(agent_task, return_exceptions=True)

    assert captured == ["42:99"]
    assert result.action == "ignore"
