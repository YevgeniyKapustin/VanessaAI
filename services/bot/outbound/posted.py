"""Tell the agent what a late follow-up really posted, for the chat history.

The worker sends a follow-up (Hermes, reminders) straight to the bot, so
the agent's chat history never gets it. After the posts, the bot sends one
``PostedMessages`` record on the ``turns`` stream. The agent saves each
text as Vanessa's own message. Fail-open: a lost record never touches the
posts, and the record never posts anything.
"""

from __future__ import annotations

import logging
from datetime import datetime

from vanessa.contracts import OutboundMessage, PostedMessages

logger = logging.getLogger("services.bot.outbound.consumer")


def posted_texts(message: OutboundMessage, *, delivered: bool, more: int) -> list[str]:
    """The texts the chat got: the main text, then the first ``more`` extras.

    With a file the text goes out as its caption or as a separate message
    even when the file fails, the same rule as ``should_post_more``.
    """
    if not delivered and message.document is None:
        return []
    return [message.text, *message.more_texts[:more]]


def posted_record(
    message: OutboundMessage, texts: list[str], posted_at: datetime
) -> PostedMessages | None:
    """The record for the agent; None when the chat got nothing.

    The id comes from the follow-up id, so a redelivery stays one record.
    """
    if not texts:
        return None
    return PostedMessages(
        message_id=f"posted:{message.message_id}",
        correlation_id=message.correlation_id,
        channel=message.channel,
        telegram_chat_id=message.telegram_chat_id,
        texts=texts,
        posted_at=posted_at,
        source=message.source,
        reply_to_message_id=message.reply_to_message_id,
        question=message.question,
    )


class PostedReporter:
    """Publishes ``PostedMessages`` records to the agent's ``turns`` stream."""

    def __init__(self, broker, stream: str) -> None:
        self._broker = broker
        self._stream = stream

    async def report(
        self,
        message: OutboundMessage,
        *,
        delivered: bool,
        more: int,
        posted_at: datetime,
    ) -> None:
        """Send the record. Never raises."""
        texts = posted_texts(message, delivered=delivered, more=more)
        record = posted_record(message, texts, posted_at)
        if record is None:
            return
        try:
            await self._broker.publish(self._stream, record)
        except Exception:  # the posts are out; only the history misses them
            logger.exception(
                "outbound_history_failed chat_id=%s source=%s",
                message.telegram_chat_id,
                message.source,
            )
