"""Consume late follow-ups from the ``outbound`` stream and post them.

The worker publishes an ``OutboundMessage`` when a slow job (e.g. a Hermes
run) finishes long after the turn RPC returned. The bot reads the stream
with its own consumer group and posts each message to Telegram.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from uuid import uuid4

from aiogram import Bot

from services.bot.outbound.document import post_document
from services.bot.outbound.gate import owner_allows, should_post
from services.bot.outbound.more import post_more_texts, should_post_more
from services.bot.outbound.send import post_outbound
from vanessa.config import settings
from vanessa.contracts import OutboundMessage
from vanessa.infrastructure.broker.backends import Delivery
from vanessa.infrastructure.broker.streams import BrokerStreams

logger = logging.getLogger(__name__)

OUTBOUND_GROUP = "bot-outbound"


def start_outbound_task(
    broker, streams: BrokerStreams, bot: Bot, access_guard=None
) -> asyncio.Task | None:
    """Start the outbound consume loop as a background task (None if no broker).

    ``access_guard`` (``ChatAccessGuard``) drops follow-ups to chats without
    the owner.
    """
    if broker is None or not streams.outbound:
        return None
    suffix = settings.broker_consumer_id or uuid4().hex[:6]
    return asyncio.create_task(
        run_outbound_loop(
            broker,
            bot,
            stream=streams.outbound,
            consumer=f"{OUTBOUND_GROUP}-{suffix}",
            allowed_chat_id=settings.allowed_chat_telegram_id,
            dedup=broker.dedup_guard(),
            delay_seconds=settings.bot_message_delay_seconds,
            access_guard=access_guard,
        )
    )


async def run_outbound_loop(
    broker,
    bot: Bot,
    *,
    stream: str,
    consumer: str,
    allowed_chat_id: int = 0,
    dedup=None,
    retry_seconds: float = 5.0,
    delay_seconds: float = 0.0,
    access_guard=None,
) -> None:
    """Read ``stream`` forever and post every Telegram message to its chat.

    A broker failure (e.g. Redis restart) restarts the read after
    ``retry_seconds``; only cancellation stops the loop. ``delay_seconds``
    is the pause between the messages of one item.
    """
    handler = partial(
        handle_outbound,
        bot,
        allowed_chat_id=allowed_chat_id,
        delay_seconds=delay_seconds,
        access_guard=access_guard,
    )
    logger.info("outbound_consumer_started stream=%s group=%s", stream, OUTBOUND_GROUP)
    while True:
        try:
            await broker.consume_forever(
                stream,
                OUTBOUND_GROUP,
                consumer,
                handler,
                dedup=dedup,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # keep the bot consuming after a broker failure
            logger.exception("outbound_consumer_failed stream=%s", stream)
        await asyncio.sleep(retry_seconds)


async def handle_outbound(
    bot: Bot,
    delivery: Delivery,
    *,
    allowed_chat_id: int = 0,
    delay_seconds: float = 0.0,
    access_guard=None,
) -> None:
    """Post one delivery. Never raises, so the consume loop always acks."""
    message = delivery.message
    if not should_post(message, allowed_chat_id):
        return
    if not await owner_allows(access_guard, bot, message.telegram_chat_id):
        return
    try:
        delivered, more = await _post_all(bot, message, delay_seconds)
    except Exception:  # a send failure must not redeliver
        logger.exception(
            "outbound_send_failed chat_id=%s source=%s",
            message.telegram_chat_id,
            message.source,
        )
        return
    logger.info(
        "outbound_sent chat_id=%s source=%s reply_to=%s delivered=%s len=%s "
        "more=%s/%s file=%s",
        message.telegram_chat_id,
        message.source,
        message.reply_to_message_id,
        delivered,
        len(message.text),
        more,
        len(message.more_texts),
        message.document.file_name if message.document else "-",
    )


async def _post_all(
    bot: Bot, message: OutboundMessage, delay_seconds: float
) -> tuple[bool, int]:
    """The main post (text or file), then the extra messages."""
    post = post_outbound if message.document is None else post_document
    delivered = await post(bot, message)
    if not should_post_more(message, delivered=delivered):
        return delivered, 0
    return delivered, await post_more_texts(bot, message, delay_seconds=delay_seconds)
