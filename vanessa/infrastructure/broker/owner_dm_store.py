"""Pending owner-DM questions.

When compose decides that a question for the owner must go to his private
chat, the bot sends the DM and stores what was asked and where. The owner's
reply to that DM then carries the answer back to the right chat.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

_DEFAULT_TTL_SECONDS = 7 * 24 * 3600


@dataclass(frozen=True, slots=True)
class PendingOwnerDm:
    chat_id: int
    chat_title: str | None
    question: str
    created_at: str


class OwnerDmStore:
    """Redis-backed map: (owner id, DM message id) → the relayed question."""

    def __init__(self, client, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._client = client
        self._ttl = ttl_seconds

    @staticmethod
    def _key(owner_id: int, message_id: int) -> str:
        return f"vanessa:owner_dm:{owner_id}:{message_id}"

    async def save(
        self,
        owner_id: int,
        message_id: int,
        pending: PendingOwnerDm,
    ) -> None:
        await self._client.set(
            self._key(owner_id, message_id),
            json.dumps(asdict(pending), ensure_ascii=False),
            ex=self._ttl,
        )

    async def get(self, owner_id: int, message_id: int) -> PendingOwnerDm | None:
        raw = await self._client.get(self._key(owner_id, message_id))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return PendingOwnerDm(
                chat_id=int(data["chat_id"]),
                chat_title=data.get("chat_title"),
                question=str(data["question"]),
                created_at=str(data["created_at"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
