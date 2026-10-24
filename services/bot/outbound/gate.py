"""Checks before the bot posts a late follow-up (Hermes, reminders).

The main guard: Vanessa posts only where the owner is. A follow-up goes out
only to a chat where the owner (or a co-owner) is an active member, or to
the owner's own private chat.
"""

from __future__ import annotations

import logging

from vanessa.config.owners import owner_telegram_ids
from vanessa.contracts import OutboundMessage

logger = logging.getLogger("services.bot.outbound.consumer")


def should_post(message, allowed_chat_id: int) -> bool:
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


async def owner_allows(access_guard, bot, chat_id: int | None) -> bool:
    """Whether the owner is in ``chat_id`` (no guard means no check)."""
    if access_guard is None:
        return True
    if chat_id is None:
        return False
    if chat_id in owner_telegram_ids():
        return True
    return await _owner_in_chat(access_guard, bot, chat_id)


async def _owner_in_chat(access_guard, bot, chat_id: int) -> bool:
    try:
        allowed = await access_guard.owner_in_chat(bot, chat_id)
    except Exception:  # a failed check must not post into an unknown chat
        logger.exception("outbound_owner_check_failed chat_id=%s", chat_id)
        return False
    if not allowed:
        logger.warning("outbound_dropped_no_owner chat_id=%s", chat_id)
    return allowed
