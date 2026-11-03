"""Outbound emoji reactions: Vanessa reacts to the user's message.

The composer may end its answer with ``[reaction:<emoji>]``; the pipeline strips
the marker and hands the emoji over in ``ChatProcessResult.reaction``. A
reaction is a nicety: every failure (chat settings, unknown emoji, flood
control) is logged and swallowed — it must never break the reply itself.
"""

import logging

from aiogram.types import Message as TelegramMessage
from aiogram.types import ReactionTypeEmoji

from services.bot.messages import IncomingMessage
from services.bot.messages.response import ChatProcessResult

logger = logging.getLogger("services.bot.handlers.messages")


async def apply_reaction(
    telegram_message: TelegramMessage,
    incoming: IncomingMessage,
    result: ChatProcessResult,
) -> bool:
    """Put the composed emoji on the user's message; True when it landed."""
    if not result.reaction:
        return False
    bot = telegram_message.bot
    if bot is None:
        return False
    try:
        await bot.set_message_reaction(
            chat_id=incoming.telegram_chat_id,
            message_id=incoming.telegram_message_id,
            reaction=[ReactionTypeEmoji(emoji=result.reaction)],
        )
    except Exception as exc:  # noqa: BLE001 - never fail a turn over a reaction
        logger.info(
            "reaction_failed chat_id=%s emoji=%s error=%s",
            incoming.telegram_chat_id,
            result.reaction,
            exc,
        )
        return False
    logger.info(
        "reaction_sent chat_id=%s message_id=%s emoji=%s",
        incoming.telegram_chat_id,
        incoming.telegram_message_id,
        result.reaction,
    )
    return True


def has_other_output(result: ChatProcessResult) -> bool:
    """Whether the turn produced anything besides the reaction."""
    return bool(
        result.reply
        or result.messages
        or result.sticker_tag
        or result.photo_file_id
        or result.owner_dm_text
    )
