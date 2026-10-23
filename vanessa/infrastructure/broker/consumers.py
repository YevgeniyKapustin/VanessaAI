"""Consumer-group hygiene: dead consumers and abandoned pending entries.

Every process start uses a new consumer name, and Redis keeps the old names
forever. A consumer with no pending entries holds nothing, so removing it is
safe: ``XREADGROUP`` recreates a name on its next read. A consumer that still
holds entries is never removed.

Nothing in this code base claims entries from a dead consumer, so a pending
entry that no one touched for the whole retention window is abandoned. Such
an entry goes to the DLQ with its payload and is then acked, so the age trim
and the consumer cleanup are not blocked by it forever.
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from vanessa.infrastructure.broker.redis_entries import (
    _raw_dlq_fields,
    _redis_text,
    _xadd_dlq,
)
from vanessa.infrastructure.broker.retention import group_name, stream_groups
from vanessa.infrastructure.observability.metrics import record_broker_dlq

logger = logging.getLogger(__name__)

ABANDONED_ERROR = "abandoned pending entry"


def _is_dead(consumer: dict, idle_ms: int) -> bool:
    return not int(consumer.get("pending") or 0) and int(
        consumer.get("idle") or 0
    ) >= idle_ms


async def _prune_group(
    client: aioredis.Redis, stream: str, group: str, idle_ms: int
) -> int:
    removed = 0
    for consumer in await client.xinfo_consumers(stream, group):
        if not _is_dead(consumer, idle_ms):
            continue
        name = str(_redis_text(consumer["name"]))
        dropped = int(await client.xgroup_delconsumer(stream, group, name))
        if dropped:
            # Read between XINFO and DELCONSUMER; the handler still ran.
            logger.warning(
                "broker_consumer_pruned_with_pending stream=%s consumer=%s n=%s",
                stream,
                name,
                dropped,
            )
        removed += 1
    return removed


async def prune_idle_consumers(
    client: aioredis.Redis, stream: str, *, idle_ms: int
) -> int:
    """Remove consumers with 0 pending entries idle for ``idle_ms`` or more."""
    removed = 0
    for group in await stream_groups(client, stream):
        removed += await _prune_group(client, stream, group_name(group), idle_ms)
    return removed


async def _dead_letter_one(
    client: aioredis.Redis, stream: str, group: str, entry_id: str, maxlen: int
) -> None:
    rows = await client.xrange(stream, min=entry_id, max=entry_id, count=1)
    if rows:
        fields = _raw_dlq_fields(rows[0][1], stream, ABANDONED_ERROR)
        await _xadd_dlq(client, stream, fields, maxlen=maxlen)
        record_broker_dlq(stream)
    await client.xack(stream, group, entry_id)
    logger.error(
        "broker_dlq_abandoned stream=%s group=%s id=%s", stream, group, entry_id
    )


async def _abandoned_in_group(
    client: aioredis.Redis, stream: str, group: str, idle_ms: int, maxlen: int
) -> int:
    entries = await client.xpending_range(
        stream, group, min="-", max="+", count=100, idle=idle_ms
    )
    for entry in entries:
        entry_id = str(_redis_text(entry["message_id"]))
        await _dead_letter_one(client, stream, group, entry_id, maxlen)
    return len(entries)


async def dead_letter_abandoned(
    client: aioredis.Redis, stream: str, *, idle_ms: int, maxlen: int
) -> int:
    """Move pending entries idle for ``idle_ms`` to the DLQ, then ack them."""
    moved = 0
    for group in await stream_groups(client, stream):
        if int(group.get("pending") or 0):
            moved += await _abandoned_in_group(
                client, stream, group_name(group), idle_ms, maxlen
            )
    return moved
