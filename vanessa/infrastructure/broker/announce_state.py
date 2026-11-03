"""Which event each watch has already announced, one Redis key per watch.

Redis is enough: after a flush the announcer treats the current event as a
baseline and posts nothing, which is the safe direction.
"""

from __future__ import annotations


class AnnouncementState:
    """Redis-backed marker of the last announced event id."""

    def __init__(self, client, *, key: str) -> None:
        self._client = client
        self._key = key

    async def last(self) -> int | None:
        try:
            raw = await self._client.get(self._key)
        except Exception:  # noqa: BLE001 - a broken marker must not stop the loop
            return None
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    async def remember(self, event_id: int) -> None:
        await self._client.set(self._key, str(int(event_id)))


__all__ = ["AnnouncementState"]
