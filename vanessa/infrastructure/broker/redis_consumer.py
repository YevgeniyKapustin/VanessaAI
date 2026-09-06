"""Redis Streams read/ack/reject/DLQ operations."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from vanessa.infrastructure.broker.backends import Delivery
from vanessa.infrastructure.broker.redis_entries import (
    _parse_deliveries,
    _raw_dlq_fields,
    _xadd_dlq,
    _xreadgroup_or_create,
)
from vanessa.infrastructure.broker.serialization import encode
from vanessa.infrastructure.observability.metrics import record_broker_dlq

logger = logging.getLogger(__name__)


class _RedisStreamConsumer:
    """ensure_group / read / ack / reject for a Redis Streams client."""

    def __init__(
        self,
        client: aioredis.Redis,
        *,
        stream_maxlen: int,
        dlq_enabled: bool,
    ) -> None:
        self._client = client
        self._stream_maxlen = stream_maxlen
        self._dlq_enabled = dlq_enabled

    async def ensure_group(self, stream: str, group: str) -> None:
        try:
            await self._client.xgroup_create(stream, group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def read(
        self, *, stream: str, group: str, consumer: str, count: int
    ) -> list[Delivery]:
        response = await _xreadgroup_or_create(
            self._client,
            stream=stream,
            group=group,
            consumer=consumer,
            count=count,
            ensure_group=self.ensure_group,
        )
        return await _parse_deliveries(
            response, group=group, on_poison=self._dlq_raw, log=logger
        )

    async def _dlq_raw(
        self,
        stream: str,
        group: str,
        stream_id: str,
        fields: dict[str, bytes | str],
    ) -> None:
        if self._dlq_enabled:
            await _xadd_dlq(
                self._client,
                stream,
                _raw_dlq_fields(fields, stream),
                maxlen=self._stream_maxlen,
            )
        await self.ack(stream, group, stream_id)

    async def ack(self, stream: str, group: str, stream_id: str) -> None:
        await self._client.xack(stream, group, stream_id)

    async def reject(
        self, stream: str, group: str, delivery: Delivery, error: BaseException
    ) -> None:
        del stream
        if self._dlq_enabled:
            await _xadd_dlq(
                self._client,
                delivery.stream,
                {
                    **encode(delivery.message),
                    "source_stream": delivery.stream,
                    "error": str(error)[:500],
                },
                maxlen=self._stream_maxlen,
            )
            record_broker_dlq(delivery.stream)
            logger.error(
                "broker_dlq stream=%s id=%s error=%s",
                delivery.stream,
                delivery.stream_id,
                error,
            )
        await self.ack(delivery.stream, group, delivery.stream_id)
