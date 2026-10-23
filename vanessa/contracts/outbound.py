"""Late, unsolicited chat messages (worker → adapter).

A normal reply goes back over the per-request RPC stream while the bot
waits. Some answers arrive much later (a Hermes run can take an hour), so
the worker publishes them to the shared ``outbound`` stream instead and the
adapter posts them on its own.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from vanessa.contracts.messages import BrokerMessage

#: Hard wire cap for a document body; the worker setting is lower.
DOCUMENT_MAX_CHARS = 2_000_000
#: A safe name: letters, digits, ``_`` and ``-``, then ``.html``.
DOCUMENT_NAME_PATTERN = r"^[\w-]{1,60}\.html$"


class OutboundDocument(BaseModel):
    """One generated text file to post as a Telegram document."""

    file_name: str = Field(pattern=DOCUMENT_NAME_PATTERN)
    content: str = Field(min_length=1, max_length=DOCUMENT_MAX_CHARS)
    mime_type: Literal["text/html"] = "text/html"


class OutboundMessage(BrokerMessage):
    """One text message the adapter must post to a chat."""

    kind: ClassVar[str] = "outbound_message"

    channel: Literal["telegram", "vrchat"] = "telegram"
    telegram_chat_id: int
    #: The message, or the document caption when ``document`` is set.
    text: str = Field(min_length=1, max_length=4096)
    #: Reply target in the chat (the user's original message), if known.
    reply_to_message_id: int | None = None
    #: Producer tag for logs/metrics, e.g. ``"hermes"``.
    source: str = "unknown"
    #: A file to send with the text (e.g. a generated HTML report).
    document: OutboundDocument | None = None
