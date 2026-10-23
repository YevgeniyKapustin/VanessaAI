import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from redis.exceptions import ResponseError

from services.agent.broker_worker.replies import ReplyPublisher
from vanessa.contracts.messages import TurnRequest
from vanessa.core.turn import ConversationTurnResult
from vanessa.infrastructure.broker.backends import Delivery
from vanessa.infrastructure.broker.consumers import (
    ABANDONED_ERROR,
    dead_letter_abandoned,
    prune_idle_consumers,
)
from vanessa.infrastructure.broker.janitor import BrokerJanitor
from vanessa.infrastructure.broker.redis_streams import RedisStreamBroker
from vanessa.infrastructure.broker.retention import (
    expire_reply_keys,
    parse_id,
    server_now_ms,
    stream_groups,
    trim_by_age,
    trim_cutoff,
)
from vanessa.infrastructure.broker.streams import BrokerStreams

_TTL = 300
_OLD_TTL = 50
_PAIR = 2


@pytest.fixture
def client():
    return fakeredis.aioredis.FakeRedis()


def _request(correlation_id: str = "c1") -> TurnRequest:
    return TurnRequest(
        correlation_id=correlation_id,
        telegram_chat_id=1,
        message="hi",
        sender_telegram_id=2,
        reply_to=f"vanessa:replies:bot-1:{correlation_id}",
    )


async def _consume_once(broker, stream, handler) -> None:
    task = asyncio.create_task(
        broker.consume_forever(stream, "g", "c-1", handler, poll_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def _seed(client, stream: str, ids: list[int]) -> None:
    for ms in ids:
        await client.xadd(stream, {"n": str(ms)}, id=f"{ms}-0")


async def test_delete_on_ack_removes_delivered_entry(client) -> None:
    broker = RedisStreamBroker("redis://x", client=client, delete_on_ack=("out",))
    await broker.publish("out", _request())
    await broker.publish("keep", _request("c2"))
    await _consume_once(broker, "out", AsyncMock())
    await _consume_once(broker, "keep", AsyncMock())
    assert await client.xlen("out") == 0
    assert await client.xlen("keep") == 1


async def test_delete_on_ack_failed_delivery_reaches_dlq(client) -> None:
    broker = RedisStreamBroker("redis://x", client=client, delete_on_ack=("out",))
    await broker.publish("out", _request())

    async def boom(_delivery: Delivery) -> None:
        raise RuntimeError("send failed")

    await _consume_once(broker, "out", boom)
    assert await client.xlen("out") == 0
    [(_, fields)] = await client.xrange("out:dlq")
    assert fields[b"error"] == b"send failed"
    assert fields[b"source_stream"] == b"out"
    assert fields[b"correlation_id"] == b"c1"


async def test_publish_with_ttl_arms_expiry(client) -> None:
    broker = RedisStreamBroker("redis://x", client=client)
    await broker.publish("r", _request(), ttl_seconds=_TTL)
    await broker.publish("plain", _request())
    assert 0 < await client.ttl("r") <= _TTL
    assert await client.ttl("plain") == -1


async def test_reply_publisher_sets_reply_ttl(client) -> None:
    broker = RedisStreamBroker("redis://x", client=client)
    request = _request()
    publisher = ReplyPublisher(broker)
    await publisher.started(request)
    await publisher.reply(request, ConversationTurnResult(action="silent", reason="r"))
    assert await client.xlen(request.reply_to) == _PAIR
    assert await client.ttl(request.reply_to) > 0


async def test_trim_keeps_pending_and_undelivered(client) -> None:
    await _seed(client, "s", [1000, 2000, 3000, 4000, 5000])
    await client.xgroup_create("s", "g", id="0")
    await client.xreadgroup("g", "c1", {"s": ">"}, count=4)
    await client.xack("s", "g", "1000-0", "2000-0", "4000-0")
    # 3000 is pending, 5000 is undelivered: both stay.
    trimmed = await trim_by_age(client, "s", now_ms=10_000, retention_ms=1)
    assert trimmed == _PAIR
    ids = [parse_id(entry_id) for entry_id, _ in await client.xrange("s")]
    assert ids == [(3000, 0), (4000, 0), (5000, 0)]


async def test_trim_respects_age_window(client) -> None:
    await _seed(client, "s", [1000, 9000])
    await client.xgroup_create("s", "g", id="$")
    cutoff = await trim_cutoff(client, "s", now_ms=10_000, retention_ms=5_000)
    assert cutoff == (5000, 0)
    assert await trim_by_age(client, "s", now_ms=10_000, retention_ms=5_000) == 1


async def test_trim_missing_stream_is_noop(client) -> None:
    assert await stream_groups(client, "nope") == []
    assert await trim_by_age(client, "nope", now_ms=10, retention_ms=1) == 0


async def test_stream_groups_reraises_other_errors() -> None:
    broken = SimpleNamespace(xinfo_groups=AsyncMock(side_effect=ResponseError("WRONGTYPE")))
    with pytest.raises(ResponseError):
        await stream_groups(broken, "s")


async def test_prune_keeps_consumers_with_pending(client) -> None:
    await _seed(client, "s", [1000, 2000])
    await client.xgroup_create("s", "g", id="0")
    await client.xreadgroup("g", "busy", {"s": ">"}, count=1)
    await client.xreadgroup("g", "dead", {"s": ">"}, count=1)
    await client.xack("s", "g", "2000-0")
    assert await prune_idle_consumers(client, "s", idle_ms=0) == 1
    names = [c["name"] for c in await client.xinfo_consumers("s", "g")]
    assert names == [b"busy"]
    assert await prune_idle_consumers(client, "s", idle_ms=10**9) == 0


async def test_prune_logs_race_with_pending(caplog) -> None:
    fake = SimpleNamespace(
        xinfo_groups=AsyncMock(return_value=[{"name": b"g"}]),
        xinfo_consumers=AsyncMock(return_value=[{"name": b"c", "pending": 0, "idle": 9}]),
        xgroup_delconsumer=AsyncMock(return_value=1),
    )
    assert await prune_idle_consumers(fake, "s", idle_ms=1) == 1
    assert "broker_consumer_pruned_with_pending" in caplog.text


async def test_abandoned_pending_goes_to_dlq(client) -> None:
    await _seed(client, "s", [1000, 2000])
    await client.xgroup_create("s", "g", id="0")
    await client.xreadgroup("g", "c1", {"s": ">"}, count=2)
    await asyncio.sleep(0.01)  # idle filter needs at least 1 ms
    assert await dead_letter_abandoned(client, "s", idle_ms=0, maxlen=100) == _PAIR
    rows = await client.xrange("s:dlq")
    assert [fields[b"n"] for _, fields in rows] == [b"1000", b"2000"]
    assert rows[0][1][b"error"] == ABANDONED_ERROR.encode()
    assert (await client.xpending("s", "g"))["pending"] == 0
    assert await dead_letter_abandoned(client, "s", idle_ms=0, maxlen=100) == 0


async def test_abandoned_entry_gone_from_stream_is_only_acked() -> None:
    fake = SimpleNamespace(
        xinfo_groups=AsyncMock(return_value=[{"name": b"g", "pending": 1}]),
        xpending_range=AsyncMock(return_value=[{"message_id": b"1-0"}]),
        xrange=AsyncMock(return_value=[]),
        xadd=AsyncMock(),
        xack=AsyncMock(),
    )
    assert await dead_letter_abandoned(fake, "s", idle_ms=0, maxlen=10) == 1
    fake.xadd.assert_not_awaited()
    fake.xack.assert_awaited_once_with("s", "g", "1-0")


async def test_expire_reply_keys_only_without_ttl(client) -> None:
    await client.xadd("vanessa:replies:a", {"x": "1"})
    await client.xadd("vanessa:replies:b", {"x": "1"})
    await client.expire("vanessa:replies:b", _OLD_TTL)
    armed = await expire_reply_keys(client, "vanessa:replies:*", ttl_seconds=_TTL)
    assert armed == 1
    assert _OLD_TTL < await client.ttl("vanessa:replies:a") <= _TTL
    assert await client.ttl("vanessa:replies:b") <= _OLD_TTL


def _janitor(client, **overrides) -> BrokerJanitor:
    settings = SimpleNamespace(
        broker_streams_prefix="vanessa",
        broker_stream_retention_seconds=0,
        broker_consumer_idle_seconds=0,
        broker_reply_ttl_seconds=300,
        broker_stream_maxlen=100,
        broker_janitor_poll_seconds=0.01,
        **overrides,
    )
    broker = RedisStreamBroker("redis://x", client=client)
    return broker.janitor(BrokerStreams.from_settings(settings), settings)


async def test_janitor_run_once_cleans_everything(client) -> None:
    await _seed(client, "vanessa:turns", [1000, 2000])
    await client.xgroup_create("vanessa:turns", "agent", id="0")
    await client.xreadgroup("agent", "old", {"vanessa:turns": ">"}, count=2)
    await client.xack("vanessa:turns", "agent", "1000-0")
    await client.xadd("vanessa:replies:bot:1", {"x": "1"})
    await asyncio.sleep(0.01)  # idle filter needs at least 1 ms
    await _janitor(client).run_once()
    assert await client.xlen("vanessa:turns") == 0
    assert await client.xlen("vanessa:turns:dlq") == 1
    assert await client.xinfo_consumers("vanessa:turns", "agent") == []
    assert await client.ttl("vanessa:replies:bot:1") > 0
    assert await server_now_ms(client) > 0


async def test_janitor_run_forever_survives_errors() -> None:
    janitor = BrokerJanitor(
        SimpleNamespace(time=AsyncMock(side_effect=ConnectionError("down"))),
        streams=("s", ""),
        reply_pattern="r:*",
        retention_seconds=1,
        consumer_idle_seconds=1,
        reply_ttl_seconds=1,
        dlq_maxlen=1,
        poll_seconds=0.01,
    )
    task = asyncio.create_task(janitor.run_forever())
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
