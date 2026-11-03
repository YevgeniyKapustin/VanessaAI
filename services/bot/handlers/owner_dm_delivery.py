"""Send the compose model's proxy question to the owner's private chat.

The DM is a normal Telegram message. Its id is remembered with the source
chat and the question, so the owner's reply can go back to the right chat.
The DM is also reported as Vanessa's message, so her private session sees it
on the next turn.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import Message

from services.bot.container import BotServices
from services.bot.messages import IncomingMessage
from services.bot.messages.response import ChatProcessResult
from services.bot.outbound.posted import PostedReporter
from services.bot.telegram_format import markdown_to_telegram_html
from vanessa.config.settings import settings
from vanessa.contracts import OutboundMessage
from vanessa.infrastructure.broker.owner_dm_store import PendingOwnerDm

logger = logging.getLogger(__name__)


async def deliver_owner_dm_action(
    message: Message,
    incoming: IncomingMessage,
    services: BotServices,
    result: ChatProcessResult,
) -> ChatProcessResult:
    """Send the owner DM when compose asked for one; never raises."""
    text = result.owner_dm_text
    owner_id = settings.required_user_telegram_id
    if not text or not owner_id or owner_id == incoming.sender_telegram_id:
        return replace(result, owner_dm_text=None) if text else result
    sent = await _send_dm(message, incoming, owner_id, text)
    if sent is not None:
        await _remember_question(services, owner_id, sent, incoming)
        await _report_posted(services, owner_id, text)
    return replace(result, owner_dm_text=None)


async def _send_dm(
    message: Message,
    incoming: IncomingMessage,
    owner_id: int,
    text: str,
) -> Message | None:
    try:
        return await message.bot.send_message(
            owner_id,
            markdown_to_telegram_html(text),
            parse_mode=ParseMode.HTML,
        )
    except TelegramBadRequest:
        return await _send_plain(message, incoming, owner_id, text)
    except TelegramAPIError:
        logger.exception(
            "owner_dm_failed owner_id=%s source_chat=%s",
            owner_id,
            incoming.telegram_chat_id,
        )
        return None


async def _send_plain(
    message: Message,
    incoming: IncomingMessage,
    owner_id: int,
    text: str,
) -> Message | None:
    try:
        return await message.bot.send_message(owner_id, text)
    except TelegramAPIError:
        logger.exception(
            "owner_dm_failed owner_id=%s source_chat=%s",
            owner_id,
            incoming.telegram_chat_id,
        )
        return None


async def _remember_question(
    services: BotServices,
    owner_id: int,
    sent: Message,
    incoming: IncomingMessage,
) -> None:
    if services.broker is None:
        return
    pending = PendingOwnerDm(
        chat_id=incoming.telegram_chat_id,
        chat_title=incoming.chat_title,
        question=incoming.text[:4096],
        created_at=datetime.now(UTC).isoformat(),
    )
    try:
        await services.broker.owner_dm_store().save(owner_id, sent.message_id, pending)
    except Exception:  # the DM is out; the relay just loses its thread
        logger.exception(
            "owner_dm_pending_failed owner_id=%s source_chat=%s",
            owner_id,
            incoming.telegram_chat_id,
        )


async def _report_posted(
    services: BotServices,
    owner_id: int,
    text: str,
) -> None:
    if services.broker is None or services.streams is None:
        return
    if not services.streams.turns:
        return
    outbound = OutboundMessage(
        telegram_chat_id=owner_id,
        text=text,
        source="owner_dm",
    )
    reporter = PostedReporter(services.broker, services.streams.turns)
    await reporter.report(
        outbound,
        delivered=True,
        more=0,
        posted_at=datetime.now(UTC),
    )
