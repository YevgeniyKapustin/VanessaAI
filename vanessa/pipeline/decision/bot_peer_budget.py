"""Loop guard for talk with other AI bots.

Telegram requires bots that talk to bots to stop reply loops. The budget
keeps three limits per chat:

- depth: at most ``max_in_row`` replies in a row to one peer bot; a message
  from a person resets the count for that chat;
- cooldown: no reply to one peer bot sooner than ``cooldown_seconds`` after
  the last one (the message is skipped, not delayed);
- hourly cap: at most ``max_per_hour`` replies to bots per chat per hour.

A limit of zero or less turns that check off. State is in memory: one
budget lives for the agent process (``DecisionStack``).
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

_HOUR_SECONDS = 3600.0


@dataclass(frozen=True, slots=True)
class BotPeerLimits:
    max_in_row: int = 3
    cooldown_seconds: float = 10.0
    max_per_hour: int = 20


class BotPeerBudget:
    def __init__(
        self,
        limits: BotPeerLimits | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limits = limits or BotPeerLimits()
        self._clock = clock
        self._in_row: dict[tuple[str, int], int] = {}
        self._last: dict[tuple[str, int], float] = {}
        self._hourly: dict[str, deque[float]] = {}

    def note_human(self, chat_key: str) -> None:
        """A person wrote in the chat: reset the in-a-row counts there."""
        for key in [key for key in self._in_row if key[0] == chat_key]:
            del self._in_row[key]

    def blocked_reason(self, chat_key: str, bot_id: int) -> str | None:
        limits = self._limits
        key = (chat_key, bot_id)
        now = self._clock()
        if 0 < limits.max_in_row <= self._in_row.get(key, 0):
            return "depth"
        if self._cooling(key, now):
            return "cooldown"
        if 0 < limits.max_per_hour <= len(self._recent(chat_key, now)):
            return "hourly"
        return None

    def allows(self, chat_key: str, bot_id: int) -> bool:
        return self.blocked_reason(chat_key, bot_id) is None

    def record_reply(self, chat_key: str, bot_id: int, *, count: int = 1) -> None:
        """Vanessa answered ``bot_id``; ``count`` > 1 for extra follow-ups."""
        key = (chat_key, bot_id)
        now = self._clock()
        self._in_row[key] = self._in_row.get(key, 0) + count
        self._last[key] = now
        stamps = self._hourly.setdefault(chat_key, deque())
        stamps.extend([now] * max(1, count))

    def _cooling(self, key: tuple[str, int], now: float) -> bool:
        last = self._last.get(key)
        cooldown = self._limits.cooldown_seconds
        return cooldown > 0 and last is not None and now - last < cooldown

    def _recent(self, chat_key: str, now: float) -> deque[float]:
        stamps = self._hourly.get(chat_key)
        if stamps is None:
            return deque()
        while stamps and now - stamps[0] >= _HOUR_SECONDS:
            stamps.popleft()
        return stamps
