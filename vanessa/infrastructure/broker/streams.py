"""Broker stream naming.

Centralizing the stream names keeps the transport wiring consistent between
producers and consumers (bot ↔ agent-core ↔ worker).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BrokerStreams:
    """Resolved stream names for one broker prefix."""

    prefix: str
    turns: str
    tasks: str

    @classmethod
    def from_settings(cls, settings) -> BrokerStreams:
        prefix = settings.broker_streams_prefix
        return cls(prefix=prefix, turns=f"{prefix}:turns", tasks=f"{prefix}:tasks")

    def reply(self, bot_id: str, correlation_id: str) -> str:
        """Private per-request reply channel for RPC (agent-core → this bot)."""
        return f"{self.prefix}:replies:{bot_id}:{correlation_id}"
