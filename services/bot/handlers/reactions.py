"""Chat reactions: remember who reacted to what, so Vanessa notices them.

Telegram delivers reactions as separate updates (``message_reaction``), not as
part of the message. The bot forwards each one to the worker as a background
task; the worker stores it as a ``reaction`` row in the chat's history, where
the composer sees it as ``<reaction sender="…" emoji="🔥" to="…"/>``.
"""

import logging
from typing import Any

from aiogram import Router
from aiogram.types import MessageReactionUpdated

from services.bot.container import BotServices

logger = logging.getLogger("services.bot.handlers.messages")


def reaction_emoji(reactions: Any) -> str:
    """The emoji of a reaction set (``""`` when the reaction was removed)."""
    emoji: list[str] = []
    for reaction in reactions or ():
        value = getattr(reaction, "emoji", None)
        if value:
            emoji.append(str(value))
    return " ".join(emoji)


def reaction_user_name(user: Any) -> str:
    if user is None:
        return ""
    full = " ".join(
        part for part in (user.first_name, user.last_name) if part
    ).strip()
    return full or (user.username or "")


def _chat_type(chat: Any) -> str:
    chat_type = getattr(chat, "type", "")
    return str(getattr(chat_type, "value", chat_type))


def reaction_payload(update: MessageReactionUpdated) -> dict[str, Any] | None:
    """The task payload for one reaction update, or None when nothing to store."""
    emoji = reaction_emoji(update.new_reaction)
    if not emoji:
        # The reaction was taken back — there is nothing new to remember.
        return None
    user = update.user
    return {
        "telegram_chat_id": update.chat.id,
        "chat_type": _chat_type(update.chat),
        "message_id": update.message_id,
        "user_id": user.id if user is not None else None,
        "user_name": reaction_user_name(user),
        "emoji": emoji,
    }


async def _report(
    services: BotServices,
    update: MessageReactionUpdated,
    payload: dict[str, Any],
) -> None:
    reporter = getattr(services.chat_client, "report_reaction", None)
    if reporter is None:
        return
    try:
        await reporter(payload)
    except Exception:
        logger.exception(
            "reaction_report_failed chat_id=%s message_id=%s",
            update.chat.id,
            update.message_id,
        )
        return
    logger.info(
        "reaction_reported chat_id=%s message_id=%s emoji=%s",
        update.chat.id,
        update.message_id,
        payload["emoji"],
    )


async def record_reaction(
    services: BotServices, update: MessageReactionUpdated
) -> None:
    if not services.access_guard.chat_allowed(update.chat.id):
        logger.info(
            "reaction_ignored chat_id=%s message_id=%s",
            update.chat.id,
            update.message_id,
        )
        return
    payload = reaction_payload(update)
    if payload is None:
        return
    await _report(services, update, payload)


def create_reactions_router(services: BotServices) -> Router:
    router = Router()

    @router.message_reaction()
    async def handle_reaction(update: MessageReactionUpdated) -> None:
        await record_reaction(services, update)

    return router
