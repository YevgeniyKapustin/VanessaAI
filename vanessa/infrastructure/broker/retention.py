"""Age-based stream trimming that never cuts pending or undelivered entries.

``XTRIM MINID`` drops every entry older than the cut-off id. The cut-off is
the oldest of: the age window, each group's oldest pending entry, and the
first entry each group has not read yet. So an entry that a consumer still
holds, or that no consumer has read yet, always stays in the stream.
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from vanessa.infrastructure.broker.redis_entries import _redis_text

type StreamId = tuple[int, int]


def parse_id(raw: Any) -> StreamId:
    """``b"1700000000000-3"`` → ``(1700000000000, 3)``."""
    ms, _, seq = str(_redis_text(raw)).partition("-")
    return int(ms), int(seq or 0)


def format_id(stream_id: StreamId) -> str:
    return f"{stream_id[0]}-{stream_id[1]}"


async def server_now_ms(client: aioredis.Redis) -> int:
    """Redis server clock in ms (stream ids use it, not the local clock)."""
    seconds, micros = await client.time()
    return int(seconds) * 1000 + int(micros) // 1000


async def stream_groups(client: aioredis.Redis, stream: str) -> list[dict]:
    """``XINFO GROUPS``; a missing stream has no groups."""
    try:
        return list(await client.xinfo_groups(stream))
    except ResponseError as exc:
        if "no such key" not in str(exc).lower():
            raise
        return []


def group_name(group: dict) -> str:
    return str(_redis_text(group["name"]))


async def _group_floor(client: aioredis.Redis, stream: str, group: dict) -> StreamId:
    # Everything up to the last delivered id was read; the next id is the
    # first entry this group has not seen yet.
    ms, seq = parse_id(group.get("last-delivered-id") or "0-0")
    floor = (ms, seq + 1)
    if not int(group.get("pending") or 0):
        return floor
    summary = await client.xpending(stream, group_name(group))
    oldest = summary.get("min") if isinstance(summary, dict) else None
    return min(floor, parse_id(oldest)) if oldest else floor


async def trim_cutoff(
    client: aioredis.Redis, stream: str, *, now_ms: int, retention_ms: int
) -> StreamId:
    """Oldest id that must stay: age window capped by every group's floor."""
    cutoff = (max(now_ms - retention_ms, 0), 0)
    for group in await stream_groups(client, stream):
        cutoff = min(cutoff, await _group_floor(client, stream, group))
    return cutoff


async def trim_by_age(
    client: aioredis.Redis, stream: str, *, now_ms: int, retention_ms: int
) -> int:
    """Drop handled entries older than ``retention_ms``; return the count."""
    cutoff = await trim_cutoff(
        client, stream, now_ms=now_ms, retention_ms=retention_ms
    )
    return int(
        await client.xtrim(stream, minid=format_id(cutoff), approximate=False)
    )


async def expire_reply_keys(
    client: aioredis.Redis, pattern: str, *, ttl_seconds: int
) -> int:
    """Give a TTL to reply streams that have none (keys from older code)."""
    armed = 0
    async for key in client.scan_iter(match=pattern, count=200):
        armed += int(bool(await client.expire(key, ttl_seconds, nx=True)))
    return armed
