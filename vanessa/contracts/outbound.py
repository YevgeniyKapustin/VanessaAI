"""Late, unsolicited chat messages (worker → adapter).

A normal reply goes back over the per-request RPC stream while the bot
waits. Some answers arrive much later (a Hermes run can take an hour), so
the worker publishes them to the shared ``outbound`` stream instead and the
adapter posts them on its own.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, Field

from vanessa.contracts.messages import BrokerMessage

#: Hard wire cap for a document body; the worker setting is lower.
DOCUMENT_MAX_CHARS = 2_000_000
#: One Telegram message.
MESSAGE_MAX_CHARS = 4096
#: The most extra messages one outbound item may carry.
MORE_TEXTS_MAX = 11
MessageText = Annotated[str, Field(min_length=1, max_length=MESSAGE_MAX_CHARS)]
#: A safe name: letters, digits, ``_`` and ``-``, then ``.html``.
DOCUMENT_NAME_PATTERN = r"^[\w-]{1,60}\.html$"


class OutboundDocument(BaseModel):
    """One generated text file to post as a Telegram document."""

    file_name: str = Field(pattern=DOCUMENT_NAME_PATTERN)
    content: str = Field(min_length=1, max_length=DOCUMENT_MAX_CHARS)
    mime_type: Literal["text/html"] = "text/html"


class OutboundMessage(BrokerMessage):
    """One late reply the adapter must post to a chat.

    ``text`` goes first (as the file caption when ``document`` is set),
    then each of ``more_texts`` as a separate message, in order.
    """

    kind: ClassVar[str] = "outbound_message"

    channel: Literal["telegram", "vrchat"] = "telegram"
    telegram_chat_id: int
    #: The message, or the document caption when ``document`` is set.
    text: MessageText
    #: Reply target in the chat (the user's original message), if known.
    reply_to_message_id: int | None = None
    #: Producer tag for logs/metrics, e.g. ``"hermes"``.
    source: str = "unknown"
    #: A file to send with the text (e.g. a generated HTML report).
    document: OutboundDocument | None = None
    #: More short messages, posted in order after ``text`` (and the file).
    more_texts: list[MessageText] = Field(
        default_factory=list, max_length=MORE_TEXTS_MAX
    )
