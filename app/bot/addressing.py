from dataclasses import dataclass

from aiogram.types import Message as TelegramMessage


@dataclass(frozen=True, slots=True)
class AddressingSignals:
    mentions_bot: bool = False
    reply_to_bot: bool = False

    @property
    def directly_addressed(self) -> bool:
        return self.mentions_bot or self.reply_to_bot


def extract_addressing(message: TelegramMessage) -> AddressingSignals:
    bot = message.bot
    bot_id = bot.id if bot is not None else None
    bot_username = (bot.username or "").lower() if bot is not None else ""
    text = message.text or ""

    reply_to_bot = False
    if (
        bot_id is not None
        and message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
    ):
        reply_to_bot = message.reply_to_message.from_user.id == bot_id

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
    )
