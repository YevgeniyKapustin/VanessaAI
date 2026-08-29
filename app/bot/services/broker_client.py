"""Redis Streams RPC transport for the bot.

Implements ``ChatApiClientProtocol`` so the handler code is identical to the
HTTP path — the bot publishes a ``TurnRequest`` and blocks on its private
reply stream until the agent core answers (with ``TurnStarted`` fired through
``on_started`` so the "typing..." indicator behaves exactly as over HTTP).
"""

from __future__ import annotations

import logging
from uuid import uuid4

from app.bot.messages import IncomingMessage
from app.bot.messages.response import ChatProcessResult
from app.broker.streams import BrokerStreams
from app.contracts.messages import TurnImage, TurnReply, TurnRequest, TurnStarted

logger = logging.getLogger(__name__)


class BrokerTurnClient:
    def __init__(
        self,
        broker,
        *,
        streams: BrokerStreams,
        timeout: float,
        bot_id: str | None = None,
    ) -> None:
        self._broker = broker
        self._streams = streams
        self._timeout = timeout
        self._bot_id = bot_id or f"bot-{uuid4().hex[:8]}"

    async def process(
        self,
        message: IncomingMessage,
        on_started=None,
    ) -> ChatProcessResult:
        correlation_id = f"{message.telegram_chat_id}:{message.telegram_message_id}"
        request = TurnRequest(
            correlation_id=correlation_id,
            telegram_chat_id=message.telegram_chat_id,
            message=message.text,
            sender_telegram_id=message.sender_telegram_id,
            chat_title=message.chat_title,
            chat_type=message.chat_type,
            sender_username=message.sender_username,
            sender_first_name=message.sender_first_name,
            sender_last_name=message.sender_last_name,
            mentions_bot=message.mentions_bot,
            reply_to_bot=message.reply_to_bot,
            reply_to_other_user=message.reply_to_other_user,
            reply_to_sender_telegram_id=message.reply_to_sender_telegram_id,
            reply_to_message_id=message.reply_to_message_id,
            reply_to_text=message.reply_to_text,
            reply_to_sender_name=message.reply_to_sender_name,
            images=[
                TurnImage(
                    data_url=image.data_url,
                    mime_type=image.mime_type,
                    telegram_file_id=image.telegram_file_id,
                )
                for image in message.images
            ],
            reply_to=self._streams.reply(self._bot_id, correlation_id),
        )

        async def on_message(msg) -> None:
            if isinstance(msg, TurnStarted) and on_started is not None:
                try:
                    await on_started()
                except Exception:
                    logger.warning("on_started_callback_failed", exc_info=True)

        reply = await self._broker.request(
            self._streams.turns,
            request,
            timeout=self._timeout,
            expect=TurnReply,
            on_message=on_message,
        )
        return ChatProcessResult(
            action=reply.action,
            reason=reply.reason,
            reply=reply.reply,
            messages=reply.messages,
            relevance_score=reply.relevance_score,
            sticker_tag=reply.sticker_tag,
            photo_file_id=reply.photo_file_id,
            photo_data_url=reply.photo_data_url,
        )
