"""Redis-backed idempotency guard for broker messages."""

import redis.asyncio as aioredis


class RedisDedupGuard:
    """SET NX EX dedup guard backed by the same Redis client as the broker."""

    def __init__(self, client: aioredis.Redis, *, ttl_seconds: int = 3600) -> None:
        self._client = client
        self._ttl = ttl_seconds

    async def acquire(self, message_id: str) -> bool:
        return bool(
            await self._client.set(f"dedup:{message_id}", "1", nx=True, ex=self._ttl)
        )
