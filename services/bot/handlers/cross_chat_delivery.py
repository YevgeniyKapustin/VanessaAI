"""Validate and deliver an agent-requested cross-chat message."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime

from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from services.bot.container import BotServices
from services.bot.messages import IncomingMessage
from services.bot.messages.response import ChatProcessResult
from services.bot.outbound.posted import PostedReporter
from services.bot.outbound.send import post_outbound
from vanessa.config.owners import is_owner
from vanessa.contracts import OutboundMessage

logger = logging.getLogger(__name__)
_GROUP_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}


async def deliver_cross_chat_action(
    message: Message,
    incoming: IncomingMessage,
    services: BotServices,
    result: ChatProcessResult,
) -> ChatProcessResult:
    target = result.outbound_chat_id
    text = result.outbound_text
    if target is None or not text:
        return result
    sent = await _send_to_target(message, incoming, services, target, text)
    reply = _delivery_reply(sent=sent)
    return replace(result, reply=reply, messages=[reply])


def _delivery_reply(*, sent: bool) -> str:
    if not sent:
        return "Не смогла отправить сообщение в другую группу."
    return "Отправила сообщение в другую группу."


async def _send_to_target(
    message: Message,
    incoming: IncomingMessage,
    services: BotServices,
    target: int,
    text: str,
) -> bool:
    if not _owner_requested_another_chat(incoming, target):
        return False
    try:
        allowed = await _target_is_available(
            message, services, target
        )
    except TelegramAPIError:
        logger.exception(
            "agent_cross_chat_failed source_chat=%s target_chat=%s",
            incoming.telegram_chat_id,
            target,
        )
        return False
    if not allowed:
        return False
    return await _post_message(message, incoming, services, target, text)


async def _post_message(
    message: Message,
    incoming: IncomingMessage,
    services: BotServices,
    target: int,
    text: str,
) -> bool:
    outbound = OutboundMessage(
        telegram_chat_id=target,
        text=text,
        source="agent_cross_chat",
    )
    try:
        delivered = await post_outbound(message.bot, outbound)
    except TelegramAPIError:
        logger.exception(
            "agent_cross_chat_failed source_chat=%s target_chat=%s",
            incoming.telegram_chat_id,
            target,
        )
        return False
    if not delivered:
        return False
    await _report_posted(services, outbound)
    logger.info(
        "agent_cross_chat_sent source_chat=%s target_chat=%s sender=%s chars=%s",
        incoming.telegram_chat_id,
        target,
        incoming.sender_telegram_id,
        len(text),
    )
    return True


def _owner_requested_another_chat(
    incoming: IncomingMessage,
    target: int,
) -> bool:
    return (
        is_owner(incoming.sender_telegram_id)
        and target != incoming.telegram_chat_id
    )


async def _target_is_available(
    message: Message,
    services: BotServices,
    target: int,
) -> bool:
    if not await services.access_guard.owner_in_chat(message.bot, target):
        return False
    target_chat = await message.bot.get_chat(target)
    if target_chat.type not in _GROUP_TYPES:
        return False
    bot_user = await message.bot.me()
    member = await message.bot.get_chat_member(target, bot_user.id)
    status = getattr(member.status, "value", member.status)
    return status not in {"left", "kicked"} and getattr(
        member, "can_send_messages", True
    ) is not False


async def _report_posted(
    services: BotServices,
    outbound: OutboundMessage,
) -> None:
    if services.broker is None or services.streams is None:
        return
    if not services.streams.turns:
        return
    reporter = PostedReporter(services.broker, services.streams.turns)
    await reporter.report(
        outbound,
        delivered=True,
        more=0,
        posted_at=datetime.now(UTC),
    )
