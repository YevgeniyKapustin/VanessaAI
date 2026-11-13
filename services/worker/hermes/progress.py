"""The "still looking" lines while a Hermes job outlives the patience window.

The chat already got a short ack when the lookup started; a run that takes
minutes would otherwise stay silent until the answer. Human chats get the
line again every ``HERMES_PROGRESS_SECONDS``, and the text carries how long
it has been going: ``{minutes}`` in ``progress_line`` becomes ``7``. Agents
(``bot_peer``) never get it: a work chat must not collect chatter.
"""

from __future__ import annotations

import logging

from services.worker.hermes.compose import truncate_message
from services.worker.hermes.payload import HermesAsk
from vanessa.contracts.outbound import OutboundMessage

logger = logging.getLogger(__name__)

PROGRESS_SOURCE = "hermes_progress"
MINUTES_PLACEHOLDER = "{minutes}"


class ProgressLine:
    """Publishes one mid-job line per heartbeat; a no-op when unset."""

    def __init__(self, broker, *, stream: str, line: str) -> None:
        self._broker = broker
        self._stream = stream
        self._line = line.strip()

    async def tell(self, ask: HermesAsk, elapsed_seconds: float = 0.0) -> None:
        if not self._line or ask.bot_peer:
            return
        message = OutboundMessage(
            channel="telegram",
            telegram_chat_id=ask.telegram_chat_id,
            text=truncate_message(self._text(elapsed_seconds)),
            reply_to_message_id=ask.telegram_message_id,
            source=PROGRESS_SOURCE,
        )
        await self._broker.publish(self._stream, message)
        logger.info(
            "hermes_job_progress chat_id=%s minutes=%s",
            ask.telegram_chat_id,
            _minutes(elapsed_seconds),
        )

    def _text(self, elapsed_seconds: float) -> str:
        if MINUTES_PLACEHOLDER not in self._line:
            return self._line
        return self._line.replace(MINUTES_PLACEHOLDER, str(_minutes(elapsed_seconds)))


def _minutes(elapsed_seconds: float) -> int:
    """Whole minutes elapsed, never 0: the line only fires past the window."""
    return max(1, int(elapsed_seconds // 60))

