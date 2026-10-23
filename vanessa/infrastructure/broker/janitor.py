"""Periodic broker retention: age trim, dead consumers, reply-stream TTLs.

Runs in the worker. One pass per stream, in this order:

1. pending entries idle for the whole window go to the DLQ (then acked);
2. handled entries older than the window are trimmed (``XTRIM MINID``);
3. consumers with 0 pending entries and a long idle time are removed.

Then reply streams without a TTL get one (keys written by older code).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

import redis.asyncio as aioredis

from vanessa.infrastructure.broker.consumers import (
    dead_letter_abandoned,
    prune_idle_consumers,
)
from vanessa.infrastructure.broker.retention import (
    expire_reply_keys,
    server_now_ms,
    trim_by_age,
)
from vanessa.infrastructure.broker.streams import BrokerStreams

logger = logging.getLogger(__name__)


class BrokerJanitor:
    def __init__(
        self,
        client: aioredis.Redis,
        *,
        streams: Sequence[str],
        reply_pattern: str,
        retention_seconds: int,
        consumer_idle_seconds: int,
        reply_ttl_seconds: int,
        dlq_maxlen: int,
        poll_seconds: float = 300.0,
    ) -> None:
        self._client = client
        self._streams = tuple(stream for stream in streams if stream)
        self._reply_pattern = reply_pattern
        self._retention_ms = retention_seconds * 1000
        self._idle_ms = consumer_idle_seconds * 1000
        self._reply_ttl = reply_ttl_seconds
        self._dlq_maxlen = dlq_maxlen
        self._poll = poll_seconds

    @classmethod
    def from_settings(
        cls, client: aioredis.Redis, streams: BrokerStreams, settings
    ) -> BrokerJanitor:
        return cls(
            client,
            streams=(streams.turns, streams.tasks, streams.outbound),
            reply_pattern=f"{streams.prefix}:replies:*",
            retention_seconds=settings.broker_stream_retention_seconds,
            consumer_idle_seconds=settings.broker_consumer_idle_seconds,
            reply_ttl_seconds=settings.broker_reply_ttl_seconds,
            dlq_maxlen=settings.broker_stream_maxlen,
            poll_seconds=settings.broker_janitor_poll_seconds,
        )

    async def clean_stream(self, stream: str, now_ms: int) -> None:
        abandoned = await dead_letter_abandoned(
            self._client, stream, idle_ms=self._retention_ms, maxlen=self._dlq_maxlen
        )
        trimmed = await trim_by_age(
            self._client, stream, now_ms=now_ms, retention_ms=self._retention_ms
        )
        pruned = await prune_idle_consumers(
            self._client, stream, idle_ms=self._idle_ms
        )
        logger.info(
            "broker_janitor stream=%s trimmed=%s consumers_removed=%s abandoned=%s",
            stream,
            trimmed,
            pruned,
            abandoned,
        )

    async def run_once(self) -> None:
        now_ms = await server_now_ms(self._client)
        for stream in self._streams:
            await self.clean_stream(stream, now_ms)
        armed = await expire_reply_keys(
            self._client, self._reply_pattern, ttl_seconds=self._reply_ttl
        )
        logger.info("broker_janitor replies_ttl_set=%s", armed)

    async def run_forever(self) -> None:
        logger.info("broker_janitor_started poll_seconds=%s", self._poll)
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("broker_janitor_failed")
            await asyncio.sleep(self._poll)
