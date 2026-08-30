import asyncio

import pytest

from vanessa.contracts.messages import (
    TaskKind,
    TaskMessage,
    TurnReply,
    TurnRequest,
    TurnStarted,
)
from vanessa.infrastructure.broker.backends import Delivery
from vanessa.infrastructure.broker.errors import BrokerTimeoutError
from vanessa.infrastructure.broker.redis_streams import RedisDedupGuard, RedisStreamBroker


@pytest.fixture
def broker():
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis()
    instance = RedisStreamBroker("redis://localhost:6379/0", client=client)
    yield instance
    # No ownership of the client (fakeredis), so close is a no-op for the socket.
    asyncio.run(instance.close())


async def test_ping(broker: RedisStreamBroker) -> None:
    await broker.ping()


async def test_publish_consume_ack(broker: RedisStreamBroker) -> None:
    request = TurnRequest(
        correlation_id="c1",
        telegram_chat_id=1,
        message="hello",
        sender_telegram_id=2,
    )
    seen: list[TurnRequest] = []

    async def handler(delivery: Delivery) -> None:
        seen.append(delivery.message)  # type: ignore[arg-type]

    consumer_task = asyncio.create_task(
        broker.consume_forever(
            "turns", "agent", "worker-1", handler, poll_seconds=0.01, count=10
        )
    )
    await asyncio.sleep(0)
    await broker.publish("turns", request)
    await asyncio.sleep(0.1)
    consumer_task.cancel()
    await asyncio.gather(consumer_task, return_exceptions=True)
    assert len(seen) == 1
    assert seen[0] == request


async def test_rpc_request_reply_with_started(
    broker: RedisStreamBroker,
) -> None:
    request = TurnRequest(
        correlation_id="c2",
        telegram_chat_id=1,
        message="ping",
        sender_telegram_id=2,
        reply_to="replies:bot-1",
    )

    async def agent_side(delivery: Delivery) -> None:
        req: TurnRequest = delivery.message  # type: ignore[assignment]
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
            ),
        )

    agent_task = asyncio.create_task(
        broker.consume_forever(
            "turns", "agent", "worker-1", agent_side, poll_seconds=0.01, count=10
        )
    )
    await asyncio.sleep(0)

    started_events: list[str] = []

    def on_message(message) -> None:
        if isinstance(message, TurnStarted):
            started_events.append(message.correlation_id)

    reply = await broker.request(
        "turns",
        request,
        timeout=2.0,
        expect=TurnReply,
        on_message=on_message,
    )
    agent_task.cancel()
    await asyncio.gather(agent_task, return_exceptions=True)

    assert isinstance(reply, TurnReply)
    assert reply.reply == "pong"
    assert started_events == ["c2"]


async def test_dedup_skips_redelivery(broker: RedisStreamBroker) -> None:
    client = broker._client
    guard = RedisDedupGuard(client)
    request = TurnRequest(
        correlation_id="c3",
        telegram_chat_id=1,
        message="x",
        sender_telegram_id=2,
    )
    calls: list[str] = []

    async def handler(delivery: Delivery) -> None:
        calls.append(delivery.message.message_id)

    consumer_task = asyncio.create_task(
        broker.consume_forever(
            "turns",
            "agent",
            "worker-1",
            handler,
            dedup=guard,
            poll_seconds=0.01,
            count=10,
        )
    )
    await asyncio.sleep(0)
    await broker.publish("turns", request)
    # Redeliver the same logical message under a fresh stream id.
    await broker.publish("turns", request)
    await asyncio.sleep(0.1)
    consumer_task.cancel()
    await asyncio.gather(consumer_task, return_exceptions=True)
    assert len(calls) == 1


async def test_failing_handler_goes_to_dlq(broker: RedisStreamBroker) -> None:
    async def handler(delivery: Delivery) -> None:
        raise RuntimeError("boom")

    consumer_task = asyncio.create_task(
        broker.consume_forever(
            "turns", "agent", "worker-1", handler, poll_seconds=0.01, count=10
        )
    )
    await asyncio.sleep(0)
    await broker.publish("turns", TaskMessage(task=TaskKind.SWEEP))
    await asyncio.sleep(0.1)
    consumer_task.cancel()
    await asyncio.gather(consumer_task, return_exceptions=True)

    entries = await broker._client.xlen("turns:dlq")
    assert entries == 1


async def test_request_timeout(broker: RedisStreamBroker) -> None:
    request = TurnRequest(
        correlation_id="c4",
        telegram_chat_id=1,
        message="x",
        sender_telegram_id=2,
        reply_to="replies:bot-2",
    )
    with pytest.raises(BrokerTimeoutError):
        await broker.request("turns", request, timeout=0.2, expect=TurnReply)
