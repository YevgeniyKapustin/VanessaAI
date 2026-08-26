from dataclasses import dataclass

from aiogram.types import Message as TelegramMessage


@dataclass(frozen=True, slots=True)
class AddressingSignals:
    mentions_bot: bool = False
    reply_to_bot: bool = False
    reply_to_other_user: bool = False
    reply_to_sender_telegram_id: int | None = None
    reply_to_message_id: int | None = None
    reply_to_text: str | None = None
    reply_to_sender_name: str | None = None

    @property
    def directly_addressed(self) -> bool:
        return self.mentions_bot or self.reply_to_bot


def _bot_username(bot: object | None) -> str:
    if bot is None:
        return ""
    me = getattr(bot, "_me", None)
    if me is not None and getattr(me, "username", None):
        return str(me.username).lower()
    username = getattr(bot, "username", None)
    if username:
        return str(username).lower()
    return ""


def _reply_sender_name(from_user: object | None) -> str | None:
    if from_user is None:
        return None
    return (
        getattr(from_user, "first_name", None)
        or getattr(from_user, "last_name", None)
        or getattr(from_user, "username", None)
    )


def _reply_text(reply_to: object | None) -> str | None:
    """Best-effort text of the replied-to message (text, caption or sticker emoji)."""
    if reply_to is None:
        return None
    text = getattr(reply_to, "text", None) or getattr(reply_to, "caption", None)
    if text:
        return str(text).strip() or None
    sticker = getattr(reply_to, "sticker", None)
    if sticker is not None:
        emoji = getattr(sticker, "emoji", None)
        if emoji:
            return f"[стикер {emoji}]"
    return None


def extract_addressing(message: TelegramMessage) -> AddressingSignals:
    bot = message.bot
    bot_id = bot.id if bot is not None else None
    bot_username = _bot_username(bot)
    text = message.text or ""

    reply_to_bot = False
    reply_to_other_user = False
    reply_to_sender_telegram_id: int | None = None
    reply_to_message_id: int | None = None
    reply_to_text: str | None = None
    reply_to_sender_name: str | None = None
    reply_to = message.reply_to_message
    if bot_id is not None and reply_to is not None and reply_to.from_user is not None:
        reply_author_id = reply_to.from_user.id
        reply_to_sender_telegram_id = reply_author_id
        reply_to_bot = reply_author_id == bot_id
        reply_to_other_user = reply_author_id != bot_id
        reply_to_message_id = getattr(reply_to, "message_id", None)
        reply_to_text = _reply_text(reply_to)
        reply_to_sender_name = _reply_sender_name(reply_to.from_user)

    mentions_bot = False
    if bot_username and f"@{bot_username}" in text.lower():
        mentions_bot = True
    for entity in message.entities or []:
        if entity.type == "text_mention" and entity.user is not None and bot_id:
            if entity.user.id == bot_id:
                mentions_bot = True
        elif entity.type == "mention" and bot_username:
            fragment = text[entity.offset : entity.offset + entity.length]
            if fragment.lower().lstrip("@") == bot_username:
                mentions_bot = True

    return AddressingSignals(
        mentions_bot=mentions_bot,
        reply_to_bot=reply_to_bot,
        reply_to_other_user=reply_to_other_user,
        reply_to_sender_telegram_id=reply_to_sender_telegram_id,
        reply_to_message_id=reply_to_message_id,
        reply_to_text=reply_to_text,
        reply_to_sender_name=reply_to_sender_name,
    )
