"""Parse Redis stream entries and write dead-letter payloads."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from vanessa.infrastructure.broker.backends import Delivery
from vanessa.infrastructure.broker.serialization import decode
from vanessa.infrastructure.observability.metrics import record_broker_consume

type _OnPoison = Callable[[str, str, str, dict[str, bytes | str]], Awaitable[None]]


def _redis_text(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode()
    return value


def _dlq_field_key(key: bytes | str) -> str:
    if isinstance(key, bytes):
        return key.decode()
    return str(key)


def _dlq_field_value(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _raw_dlq_fields(
    fields: dict[str, bytes | str],
    stream: str,
    error: str = "undecodable message",
) -> dict[str, str]:
    encoded = {_dlq_field_key(key): _dlq_field_value(value) for key, value in fields.items()}
    return {
        **encoded,
        "source_stream": stream,
        "error": error,
    }


async def _xadd_dlq(
    client: aioredis.Redis,
    stream: str,
    fields: dict[str, str],
    *,
    maxlen: int,
) -> None:
    await client.xadd(
        f"{stream}:dlq",
        fields,
        maxlen=maxlen,
        approximate=True,
    )


async def _xadd_stream(
    client: aioredis.Redis,
    stream: str,
    fields: dict[str, str],
    *,
    maxlen: int,
    ttl_seconds: int = 0,
) -> Any:
    """XADD; ``ttl_seconds`` > 0 (re)arms the key TTL in the same transaction."""
    if ttl_seconds <= 0:
        return await client.xadd(stream, fields, maxlen=maxlen, approximate=True)
    async with client.pipeline(transaction=True) as pipe:
        pipe.xadd(stream, fields, maxlen=maxlen, approximate=True)
        pipe.expire(stream, ttl_seconds)
        entry_id, _ = await pipe.execute()
    return entry_id


async def _xreadgroup_or_create(
    client: aioredis.Redis,
    *,
    stream: str,
    group: str,
    consumer: str,
    count: int,
    ensure_group: Callable[[str, str], Awaitable[None]],
) -> Any:
    # Non-blocking read (no BLOCK option): the consume loop paces itself
    # with asyncio.sleep, so the event loop never hangs on the transport.
    # NOTE: BLOCK 0 means "block forever" in Redis — never pass block=0.
    try:
        return await client.xreadgroup(group, consumer, {stream: ">"}, count=count)
    except ResponseError as exc:
        if "NOGROUP" not in str(exc):
            raise
        await ensure_group(stream, group)
        return await client.xreadgroup(group, consumer, {stream: ">"}, count=count)


async def _parse_one_entry(
    stream_name: str,
    group: str,
    raw_entry_id: Any,
    fields: dict[str, bytes | str],
    *,
    on_poison: _OnPoison,
    log: logging.Logger,
) -> Delivery | None:
    entry_id = _redis_text(raw_entry_id)
    try:
        message = decode(fields)
    except Exception:
        # A poison entry must never wedge the consumer: move it to
        # the DLQ and ack it out of the main stream.
        log.exception("broker_decode_failed stream=%s id=%s", stream_name, entry_id)
        await on_poison(stream_name, group, entry_id, fields)
        return None
    delivery = Delivery(stream=stream_name, stream_id=entry_id, message=message)
    record_broker_consume(stream_name, message.message_kind())
    return delivery


async def _parse_deliveries(
    response: Any,
    *,
    group: str,
    on_poison: _OnPoison,
    log: logging.Logger,
) -> list[Delivery]:
    deliveries: list[Delivery] = []
    for raw_stream_name, entries in response or []:
        stream_name = _redis_text(raw_stream_name)
        for raw_entry_id, fields in entries:
            delivery = await _parse_one_entry(
                stream_name,
                group,
                raw_entry_id,
                fields,
                on_poison=on_poison,
                log=log,
            )
            if delivery is not None:
                deliveries.append(delivery)
    return deliveries
