"""Redis Streams RPC for bot turns and inbox notes."""

from __future__ import annotations

import base64
import logging
from typing import Any
from uuid import uuid4

from services.bot.messages import IncomingMessage
from services.bot.messages.response import ChatProcessResult
from vanessa.config.owners import is_owner
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
        await self._broker.remember_chat(
            message.telegram_chat_id,
            message.chat_title,
            message.chat_type,
        )
        known_chats = await self._broker.known_chats()
        relay = await self._pending_relay(message)
        request = TurnRequest(
            correlation_id=correlation_id,
            channel="telegram",
            telegram_chat_id=message.telegram_chat_id,
            telegram_message_id=message.telegram_message_id,
            message=message.text,
            sender_telegram_id=message.sender_telegram_id,
            chat_title=message.chat_title,
            chat_type=message.chat_type,
            known_chats=known_chats,
            sender_username=message.sender_username,
            sender_first_name=message.sender_first_name,
            sender_last_name=message.sender_last_name,
            sender_is_bot=message.sender_is_bot,
            sender_is_owner=is_owner(message.sender_telegram_id),
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
                    kind=image.kind,
                )
                for image in message.images
            ],
            reply_to=self._streams.reply(self._bot_id, correlation_id),
            relay_chat_id=relay.chat_id if relay else None,
            relay_chat_title=relay.chat_title if relay else None,
            relay_question=relay.question if relay else None,
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
            reaction=reply.reaction,
            photo_file_id=reply.photo_file_id,
            photo_data_url=reply.photo_data_url,
            outbound_chat_id=(
                reply.outbound_chat_id
                if reply.outbound_chat_id
                != message.telegram_chat_id
                and reply.outbound_chat_id
                in {chat.chat_id for chat in known_chats}
                else None
            ),
            outbound_text=(
                reply.outbound_text
                if reply.outbound_chat_id
                != message.telegram_chat_id
                and reply.outbound_chat_id
                in {chat.chat_id for chat in known_chats}
                else None
            ),
            owner_dm_text=(
                reply.owner_dm_text
                if message.sender_is_bot
                and message.chat_type in {"group", "supergroup"}
                else None
            ),
        )

    async def report_reaction(self, payload: dict[str, Any]) -> None:
        """Record a chat reaction as a background task (no reply expected)."""
        task = TaskMessage(task=TaskKind.REACTION, payload=payload)
        await self._broker.publish(self._streams.tasks, task)

    async def _pending_relay(self, message: IncomingMessage):
        """The question an owner DM replies to, when the DM carries one."""
        if message.chat_type != "private" or message.reply_to_message_id is None:
            return None
        if not is_owner(message.sender_telegram_id):
            return None
        try:
            store = self._broker.owner_dm_store()
            return await store.get(
                message.sender_telegram_id, message.reply_to_message_id
            )
        except Exception:
            logger.exception(
                "owner_dm_pending_lookup_failed owner_id=%s",
                message.sender_telegram_id,
            )
            return None

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
