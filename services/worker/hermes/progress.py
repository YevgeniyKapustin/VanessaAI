"""One "still looking" line while a Hermes job outlives the patience window.

The chat already got a short ack when the lookup started; a run that takes
minutes would otherwise stay silent until the answer. Human chats get one
extra line, agents (``bot_peer``) never do: a work chat must not collect
chatter.
"""

from __future__ import annotations

import logging

from services.worker.hermes.compose import truncate_message
from services.worker.hermes.payload import HermesAsk
from vanessa.contracts.outbound import OutboundMessage

logger = logging.getLogger(__name__)

PROGRESS_SOURCE = "hermes_progress"


class ProgressLine:
    """Publishes the mid-job line once per job; a no-op when unset."""

    def __init__(self, broker, *, stream: str, line: str) -> None:
        self._broker = broker
        self._stream = stream
        self._line = truncate_message(line)

    async def tell(self, ask: HermesAsk) -> None:
        if not self._line or ask.bot_peer:
            return
        message = OutboundMessage(
            channel="telegram",
            telegram_chat_id=ask.telegram_chat_id,
            text=self._line,
            reply_to_message_id=ask.telegram_message_id,
            source=PROGRESS_SOURCE,
        )
        await self._broker.publish(self._stream, message)
        logger.info("hermes_job_progress chat_id=%s", ask.telegram_chat_id)
