"""Redis Streams RPC for bot turns and inbox notes."""

from __future__ import annotations

import base64
import logging
from uuid import uuid4

from services.bot.messages import IncomingMessage
from services.bot.messages.response import ChatProcessResult
from vanessa.contracts.messages import (
    InboxNoteReply,
    TaskKind,
    TaskMessage,
    TurnImage,
    TurnReply,
    TurnRequest,
    TurnStarted,
)
from vanessa.infrastructure.broker.streams import BrokerStreams

logger = logging.getLogger(__name__)


class NotesError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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

    async def save_inbox_note(
        self,
        *,
        text: str,
        attachment_bytes: bytes | None = None,
        attachment_suffix: str = ".jpg",
    ) -> str:
        correlation_id = f"note:{uuid4().hex}"
        payload: dict[str, str] = {
            "text": text,
            "attachment_suffix": attachment_suffix,
        }
        if attachment_bytes:
            payload["attachment_base64"] = base64.b64encode(
                attachment_bytes
            ).decode()
        request = TaskMessage(
            correlation_id=correlation_id,
            task=TaskKind.INBOX_NOTE,
            payload=payload,
            reply_to=self._streams.reply(self._bot_id, correlation_id),
        )
        reply = await self._broker.request(
            self._streams.tasks,
            request,
            timeout=self._timeout,
            expect=InboxNoteReply,
        )
        if not isinstance(reply, InboxNoteReply) or not reply.ok:
            code = reply.error if isinstance(reply, InboxNoteReply) else "error"
            raise NotesError(code or "error")
        return str(reply.path or "")
