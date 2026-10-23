"""Post one ``OutboundMessage`` to Telegram through the normal reply path."""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import ReplyParameters

from services.bot.handlers.message_send_fallback import _deliver_reply_block
from services.bot.telegram_format import markdown_to_telegram_html
from vanessa.contracts import OutboundMessage


@dataclass(frozen=True, slots=True)
class _Chat:
    id: int


@dataclass(frozen=True, slots=True)
class ChatTarget:
    """The ``reply`` / ``answer`` / ``chat.id`` surface of an aiogram Message.

    Late follow-ups have no incoming ``Message`` object, only a chat id and
    the id of the user's original message. This target lets them reuse the
    same HTML → plain-text delivery as normal replies.
    """

    bot: Bot
    chat: _Chat
    reply_to_message_id: int | None = None

    async def reply(self, text: str, parse_mode: ParseMode | None = None) -> None:
        await self.bot.send_message(
            self.chat.id,
            text,
            parse_mode=parse_mode,
            reply_parameters=ReplyParameters(
                message_id=self.reply_to_message_id,
                allow_sending_without_reply=True,
            ),
        )

    async def answer(self, text: str, parse_mode: ParseMode | None = None) -> None:
        await self.bot.send_message(self.chat.id, text, parse_mode=parse_mode)


async def post_outbound(bot: Bot, message: OutboundMessage) -> bool:
    """Send the text; retry without a reply target if that delivery fails.

    Returns True when Telegram accepted the text. Telegram errors are logged
    by the reply-block sender and never raised.
    """
    target = ChatTarget(
        bot=bot,
        chat=_Chat(id=message.telegram_chat_id),
        reply_to_message_id=message.reply_to_message_id,
    )
    as_reply = message.reply_to_message_id is not None
    if await _deliver(target, message.text, as_reply=as_reply):
        return True
    if not as_reply:
        return False
    return await _deliver(target, message.text, as_reply=False)


async def _deliver(target: ChatTarget, text: str, *, as_reply: bool) -> bool:
    return await _deliver_reply_block(
        target,
        html=markdown_to_telegram_html(text),
        plain=text,
        as_reply=as_reply,
        index=0,
        total=1,
    )
