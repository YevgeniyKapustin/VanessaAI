"""Late, unsolicited chat messages (worker → adapter).

A normal reply goes back over the per-request RPC stream while the bot
waits. Some answers arrive much later (a Hermes run can take an hour), so
the worker publishes them to the shared ``outbound`` stream instead and the
adapter posts them on its own.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from vanessa.contracts.messages import BrokerMessage


class OutboundMessage(BrokerMessage):
    """One text message the adapter must post to a chat."""

    kind: ClassVar[str] = "outbound_message"

    channel: Literal["telegram", "vrchat"] = "telegram"
    telegram_chat_id: int
    text: str = Field(min_length=1, max_length=4096)
    #: Reply target in the chat (the user's original message), if known.
    reply_to_message_id: int | None = None
    #: Producer tag for logs/metrics, e.g. ``"hermes"``.
    source: str = "unknown"
