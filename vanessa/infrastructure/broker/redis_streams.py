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

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from vanessa.contracts.messages import BrokerMessage
from vanessa.infrastructure.broker.backends import (
    Delivery,
    StreamBackend,
)
from vanessa.infrastructure.broker.backends import (
    consume_forever as run_consume_loop,
)
from vanessa.infrastructure.broker.errors import BrokerError, BrokerTimeoutError
from vanessa.infrastructure.broker.serialization import decode, encode
from vanessa.infrastructure.observability.metrics import (
    record_broker_consume,
    record_broker_dlq,
    record_broker_publish,
    record_broker_rpc,
)

logger = logging.getLogger(__name__)


class RedisDedupGuard:
    """SET NX EX dedup guard backed by the same Redis client as the broker."""

    def __init__(self, client: aioredis.Redis, *, ttl_seconds: int = 3600) -> None:
        self._client = client
        self._ttl = ttl_seconds

    async def acquire(self, message_id: str) -> bool:
        return bool(
            await self._client.set(f"dedup:{message_id}", "1", nx=True, ex=self._ttl)
        )


class RedisStreamBroker(StreamBackend):
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
        self._dlq_enabled = dlq_enabled
        self._owns_client = client is None

    # -- StreamBackend --------------------------------------------------------

    async def ensure_group(self, stream: str, group: str) -> None:
        try:
            await self._client.xgroup_create(stream, group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def read(
        self, *, stream: str, group: str, consumer: str, count: int
    ) -> list[Delivery]:
        # Non-blocking read (no BLOCK option): the consume loop paces itself
        # with asyncio.sleep, so the event loop never hangs on the transport.
        # NOTE: BLOCK 0 means "block forever" in Redis — never pass block=0.
        try:
            response = await self._client.xreadgroup(
                group, consumer, {stream: ">"}, count=count
            )
        except ResponseError as exc:
            if "NOGROUP" in str(exc):
                await self.ensure_group(stream, group)
                response = await self._client.xreadgroup(
                    group, consumer, {stream: ">"}, count=count
                )
            else:
                raise
        deliveries: list[Delivery] = []
        for stream_name, entries in response or []:
            # Redis returns the stream name as bytes; normalize to str so the
            # DLQ naming and logging below stay consistent.
            stream_name = (
                stream_name.decode() if isinstance(stream_name, bytes) else stream_name
            )
            for entry_id, fields in entries:
                entry_id = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                try:
                    message = decode(fields)
                except Exception:
                    # A poison entry must never wedge the consumer: move it to
                    # the DLQ and ack it out of the main stream.
                    logger.exception(
                        "broker_decode_failed stream=%s id=%s", stream_name, entry_id
                    )
                    await self._dlq_raw(stream_name, group, entry_id, fields)
                    continue
                deliveries.append(
                    Delivery(stream=stream_name, stream_id=entry_id, message=message)
                )
                record_broker_consume(stream_name, message.message_kind())
        return deliveries

    async def _dlq_raw(
        self,
        stream: str,
        group: str,
        stream_id: str,
        fields: dict[str, bytes | str],
    ) -> None:
        if self._dlq_enabled:
            await self._client.xadd(
                f"{stream}:dlq",
                {
                    **{k.decode() if isinstance(k, bytes) else str(k): (
                        v.decode(errors="replace") if isinstance(v, bytes) else v
                    ) for k, v in fields.items()},
                    "source_stream": stream,
                    "error": "undecodable message",
                },
                maxlen=self._stream_maxlen,
                approximate=True,
            )
        await self.ack(stream, group, stream_id)

    async def ack(self, stream: str, group: str, stream_id: str) -> None:
        await self._client.xack(stream, group, stream_id)

    async def reject(
        self, stream: str, group: str, delivery: Delivery, error: BaseException
    ) -> None:
        if self._dlq_enabled:
            dlq = f"{delivery.stream}:dlq"
            await self._client.xadd(
                dlq,
                {
                    **encode(delivery.message),
                    "source_stream": delivery.stream,
                    "error": str(error)[:500],
                },
                maxlen=self._stream_maxlen,
                approximate=True,
            )
            record_broker_dlq(delivery.stream)
            logger.error(
                "broker_dlq stream=%s id=%s error=%s",
                delivery.stream,
                delivery.stream_id,
                error,
            )
        await self.ack(delivery.stream, group, delivery.stream_id)

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
        """Publish an RPC request and block until the expected reply arrives.

        Replies are read from ``message.reply_to`` — a private per-request
        channel — so concurrent requests never steal each other's replies.
        Intermediate messages (e.g. ``TurnStarted``) are forwarded to
        ``on_message`` and skipped.
        """
        if not message.reply_to:
            raise BrokerError("RPC request requires a reply_to stream")
        kinds = expect if isinstance(expect, tuple) else (expect,)
        expect_kinds = {model.message_kind() for model in kinds}
        await self.publish(stream, message)
        started = time.monotonic()
        reply_stream = message.reply_to
        # Start from the beginning of the PRIVATE reply stream ("0", not "$"):
        # "$" only returns entries appended after the call, so a fast reply
        # published before the first read would be missed forever.
        last_id = "0"
        deadline = started + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BrokerTimeoutError(
                    f"no {sorted(expect_kinds)} reply for "
                    f"{message.message_kind()} {message.correlation_id} "
                    f"within {timeout}s"
                )
            # Non-blocking read (no BLOCK option — BLOCK 0 would wait forever).
            response = await self._client.xread({reply_stream: last_id}, count=32)
            if not response:
                await asyncio.sleep(0.05)
                continue
            for stream_name, entries in response:
                for entry_id, fields in entries:
                    last_id = entry_id
                    decoded = decode(fields)
                    if on_message is not None:
                        result = on_message(decoded)
                        if asyncio.iscoroutine(result):
                            await result
                    if (
                        decoded.correlation_id == message.correlation_id
                        and decoded.message_kind() in expect_kinds
                    ):
                        record_broker_rpc(
                            message.message_kind(), time.monotonic() - started
                        )
                        return decoded

    def dedup_guard(self, ttl_seconds: int = 3600) -> RedisDedupGuard:
        """Idempotency guard sharing this broker's Redis client."""
        return RedisDedupGuard(self._client, ttl_seconds=ttl_seconds)

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
            self,
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
