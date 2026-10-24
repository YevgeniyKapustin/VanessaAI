"""Messages the adapter posted on its own (adapter → agent).

A late follow-up (``OutboundMessage``) goes from the worker straight to the
adapter, so the agent never sees it. After the adapter posts it, it sends
this record on the ``turns`` stream. The agent saves each posted text as
Vanessa's own message, so the next turn sees it in the chat history.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import Field

from vanessa.contracts.messages import BrokerMessage
from vanessa.contracts.outbound import (
    MORE_TEXTS_MAX,
    QUESTION_MAX_CHARS,
    MessageText,
)


class PostedMessages(BrokerMessage):
    """The texts of one follow-up that the chat really got, in order."""

    kind: ClassVar[str] = "posted_messages"

    channel: Literal["telegram", "vrchat"] = "telegram"
    telegram_chat_id: int
    #: Each posted message, in the order the chat got them.
    texts: list[MessageText] = Field(min_length=1, max_length=MORE_TEXTS_MAX + 1)
    #: When the first message went out (UTC).
    posted_at: datetime
    #: The producer tag of the follow-up, e.g. ``"hermes"``.
    source: str = "unknown"
    #: The user's message the first text replied to, if any.
    reply_to_message_id: int | None = None
    #: The work question the texts answer (Hermes), if any.
    question: str | None = Field(default=None, max_length=QUESTION_MAX_CHARS)
