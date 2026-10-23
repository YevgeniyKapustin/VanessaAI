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
from services.bot.outbound.send import post_outbound
from vanessa.config import settings
from vanessa.contracts import OutboundMessage
from vanessa.infrastructure.broker.backends import Delivery
from vanessa.infrastructure.broker.streams import BrokerStreams

logger = logging.getLogger(__name__)

OUTBOUND_GROUP = "bot-outbound"


def start_outbound_task(broker, streams: BrokerStreams, bot: Bot) -> asyncio.Task | None:
    """Start the outbound consume loop as a background task (None if no broker)."""
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
) -> None:
    """Read ``stream`` forever and post every Telegram message to its chat.

    A broker failure (e.g. Redis restart) restarts the read after
    ``retry_seconds``; only cancellation stops the loop.
    """
    handler = partial(handle_outbound, bot, allowed_chat_id=allowed_chat_id)
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
) -> None:
    """Post one delivery. Never raises, so the consume loop always acks."""
    message = delivery.message
    if not _should_post(message, allowed_chat_id):
        return
    post = post_outbound if message.document is None else post_document
    try:
        delivered = await post(bot, message)
    except Exception:  # a send failure must not redeliver
        logger.exception(
            "outbound_send_failed chat_id=%s source=%s",
            message.telegram_chat_id,
            message.source,
        )
        return
    logger.info(
        "outbound_sent chat_id=%s source=%s reply_to=%s delivered=%s len=%s file=%s",
        message.telegram_chat_id,
        message.source,
        message.reply_to_message_id,
        delivered,
        len(message.text),
        message.document.file_name if message.document else "-",
    )


def _should_post(message, allowed_chat_id: int) -> bool:
    if not isinstance(message, OutboundMessage):
        logger.warning("outbound_unexpected kind=%s", message.message_kind())
        return False
    if message.channel != "telegram":
        logger.debug("outbound_skipped channel=%s", message.channel)
        return False
    if allowed_chat_id and message.telegram_chat_id != allowed_chat_id:
        logger.warning(
            "outbound_dropped_wrong_chat chat_id=%s allowed=%s",
            message.telegram_chat_id,
            allowed_chat_id,
        )
        return False
    return True
