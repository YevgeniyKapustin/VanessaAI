"""Post the extra messages of one ``OutboundMessage`` (``more_texts``).

A late follow-up is split into short messages like a normal reply: the
first one (or the file caption) is the reply to the user, the rest follow
as plain chat messages with the same pause between them.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot

from services.bot.outbound.send import post_outbound
from vanessa.contracts import OutboundMessage


def should_post_more(message: OutboundMessage, *, delivered: bool) -> bool:
    """Go on after the main post: the text went out, or a file was tried.

    A failed file still posts its text as a normal message.
    """
    return bool(message.more_texts) and (delivered or message.document is not None)


async def post_more_texts(
    bot: Bot, message: OutboundMessage, *, delay_seconds: float
) -> int:
    """Post ``more_texts`` in order; stop on the first failure.

    Returns how many messages Telegram took.
    """
    sent = 0
    for text in message.more_texts:
        await asyncio.sleep(max(0.0, delay_seconds))
        if not await post_outbound(bot, _plain(message, text)):
            break
        sent += 1
    return sent


def _plain(message: OutboundMessage, text: str) -> OutboundMessage:
    """One extra message: not a reply, no file, nothing more after it."""
    return message.model_copy(
        update={
            "text": text,
            "reply_to_message_id": None,
            "document": None,
            "more_texts": [],
        }
    )
