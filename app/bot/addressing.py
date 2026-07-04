from dataclasses import dataclass

from aiogram.types import Message as TelegramMessage


@dataclass(frozen=True, slots=True)
class AddressingSignals:
    mentions_bot: bool = False
    reply_to_bot: bool = False
    reply_to_other_user: bool = False

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


def extract_addressing(message: TelegramMessage) -> AddressingSignals:
    bot = message.bot
    bot_id = bot.id if bot is not None else None
    bot_username = _bot_username(bot)
    text = message.text or ""

    reply_to_bot = False
    reply_to_other_user = False
    if (
        bot_id is not None
        and message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
    ):
        reply_author_id = message.reply_to_message.from_user.id
        reply_to_bot = reply_author_id == bot_id
        reply_to_other_user = reply_author_id != bot_id

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
    )
