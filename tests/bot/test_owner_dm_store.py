"""The pending owner-DM registry keeps what was asked and where."""

import fakeredis.aioredis
import pytest

from vanessa.infrastructure.broker.owner_dm_store import OwnerDmStore, PendingOwnerDm

OWNER = 999


@pytest.mark.asyncio
async def test_roundtrip() -> None:
    store = OwnerDmStore(
        fakeredis.aioredis.FakeRedis(decode_responses=True),
        ttl_seconds=60,
    )
    pending = PendingOwnerDm(
        chat_id=-1001,
        chat_title="Work chat",
        question="Когда релиз?",
        created_at="2026-10-30T10:00:00+00:00",
    )

    await store.save(OWNER, 55, pending)

    assert await store.get(OWNER, 55) == pending
    assert await store.get(OWNER, 56) is None
    assert await store.get(1000, 55) is None


@pytest.mark.asyncio
async def test_broken_payload_is_ignored() -> None:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await client.set(f"vanessa:owner_dm:{OWNER}:55", "{not json")
    store = OwnerDmStore(client, ttl_seconds=60)

    assert await store.get(OWNER, 55) is None
