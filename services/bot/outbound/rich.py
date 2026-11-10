"""Post a message as a Telegram rich message, with plain text as the fallback.

A rich message draws headings, tables and collapsible ``<details>`` blocks
inside one bubble — a deploy card instead of a wall of lines. Support is new
(Bot API 10.3 through aiogram 3.31), so any refusal, any old client, any
missing method: the same text goes out as a normal message.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import InputRichMessage, ReplyParameters

from services.bot.outbound.send import post_outbound
from vanessa.contracts import OutboundMessage
from vanessa.infrastructure.observability.metrics import record_telegram

logger = logging.getLogger(__name__)


async def post_rich(bot: Bot, message: OutboundMessage) -> bool:
    """Send ``rich_html``; True when Telegram took it.

    Without ``rich_html`` this is the ordinary text path. A refused rich
    message posts the text instead, so the chat is never left silent.
    """
    html = message.rich_html
    if not html:
        return await post_outbound(bot, message)
    sent = await _send_rich(bot, message, html)
    record_telegram("send_rich_message", "success" if sent else "error")
    if sent:
        return True
    return await post_outbound(bot, message)


async def _send_rich(bot: Bot, message: OutboundMessage, html: str) -> bool:
    try:
        await bot.send_rich_message(
            message.telegram_chat_id,
            InputRichMessage(html=html),
            reply_parameters=_reply_parameters(message),
        )
        return True
    except Exception as exc:  # noqa: BLE001 - any Telegram refusal → text
        _log_failure(message, exc)
        return False


def _reply_parameters(message: OutboundMessage) -> ReplyParameters | None:
    if message.reply_to_message_id is None:
        return None
    return ReplyParameters(
        message_id=message.reply_to_message_id, allow_sending_without_reply=True
    )


def _log_failure(message: OutboundMessage, exc: BaseException) -> None:
    # The type only: the error text may echo the message body.
    logger.warning(
        "outbound_rich_failed chat_id=%s source=%s error=%s",
        message.telegram_chat_id,
        message.source,
        type(exc).__name__,
    )


__all__ = ["post_rich"]
