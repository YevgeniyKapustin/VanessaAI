"""Redis Streams broker backend and high-level transport.

Stream layout
-------------
``turns``                bot → agent   (consumer group ``agent``)
``replies:<id>``         agent → one bot instance/request (private RPC channel)
``tasks``                agent → worker (consumer group ``worker``)
``<stream>:dlq``         dead-letter for failed deliveries

Delivery guarantees
-------------------
* At-least-once via consumer groups (a message stays pending until acked).
* Idempotency via ``message_id`` dedup (SET NX EX) in ``RedisDedupGuard``.
* Poison messages are moved to the DLQ stream and acked out of the main stream.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import redis.asyncio as aioredis

from vanessa.contracts.messages import BrokerMessage
from vanessa.infrastructure.broker.backends import (
    consume_forever as run_consume_loop,
)
from vanessa.infrastructure.broker.redis_consumer import _RedisStreamConsumer
from vanessa.infrastructure.broker.redis_rpc import _rpc_request
from vanessa.infrastructure.broker.serialization import encode
from vanessa.infrastructure.observability.metrics import record_broker_publish


class RedisDedupGuard:
    """SET NX EX dedup guard backed by the same Redis client as the broker."""

    def __init__(self, client: aioredis.Redis, *, ttl_seconds: int = 3600) -> None:
        self._client = client
        self._ttl = ttl_seconds

    async def acquire(self, message_id: str) -> bool:
        return bool(
            await self._client.set(f"dedup:{message_id}", "1", nx=True, ex=self._ttl)
        )


class RedisStreamBroker:
    """Redis Streams implementation of the broker transport."""

    def __init__(
        self,
        url: str,
        *,
        stream_maxlen: int = 100_000,
        dlq_enabled: bool = True,
        client: aioredis.Redis | None = None,
    ) -> None:
        self._client = client or aioredis.from_url(url)
        self._stream_maxlen = stream_maxlen
        self._owns_client = client is None
        self._consumer = _RedisStreamConsumer(
            self._client,
            stream_maxlen=stream_maxlen,
            dlq_enabled=dlq_enabled,
        )

    # -- Producer / RPC --------------------------------------------------------

    async def publish(self, stream: str, message: BrokerMessage) -> str:
        entry_id = await self._client.xadd(
            stream, encode(message), maxlen=self._stream_maxlen, approximate=True
        )
        record_broker_publish(stream, message.message_kind())
        return str(entry_id)

    async def request(
        self,
        stream: str,
        message: BrokerMessage,
        *,
        timeout: float,
        expect: type[BrokerMessage] | tuple[type[BrokerMessage], ...],
        on_message: Callable[[BrokerMessage], Any] | None = None,
    ) -> BrokerMessage:
        return await _rpc_request(
            self._client,
            publish=self.publish,
            stream=stream,
            message=message,
            timeout=timeout,
            expect=expect,
            on_message=on_message,
        )

    def dedup_guard(self, ttl_seconds: int = 3600) -> RedisDedupGuard:
        """Idempotency guard sharing this broker's Redis client."""
        return RedisDedupGuard(self._client, ttl_seconds=ttl_seconds)

    async def ensure_group(self, stream: str, group: str) -> None:
        await self._consumer.ensure_group(stream, group)

    # -- Queue-health probes (for the metrics collector) -------------------------

    async def stream_length(self, stream: str) -> int:
        """Number of entries currently in a stream."""
        return int(await self._client.xlen(stream))

    async def consumer_lag(self, stream: str, group: str) -> int:
        """Number of pending (unacked) entries for a consumer group."""
        try:
            pending = await self._client.xpending(stream, group)
        except Exception:  # noqa: BLE001 - group may not exist yet
            return 0
        if isinstance(pending, dict):
            return int(pending.get("pending", 0) or 0)
        return 0

    # -- Consumer loop -----------------------------------------------------------

    async def consume_forever(
        self,
        stream: str,
        group: str,
        consumer: str,
        handler,
        *,
        dedup=None,
        poll_seconds: float = 0.05,
        count: int = 1,
    ) -> None:
        await run_consume_loop(
            self._consumer,
            stream=stream,
            group=group,
            consumer=consumer,
            handler=handler,
            dedup=dedup,
            poll_seconds=poll_seconds,
            count=count,
        )

    # -- Lifecycle ---------------------------------------------------------------

    async def ping(self) -> None:
        await self._client.ping()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


__all__ = [
    "RedisDedupGuard",
    "RedisStreamBroker",
]
