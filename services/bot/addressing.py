from dataclasses import dataclass

from aiogram.types import Message as TelegramMessage

from services.bot.addressing_mentions import message_mentions_bot
from services.bot.addressing_reply import _bot_username, extract_reply_addressing


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


def extract_addressing(message: TelegramMessage) -> AddressingSignals:
    bot = message.bot
    bot_id = bot.id if bot is not None else None
    bot_username = _bot_username(bot)
    text = message.text or ""
    reply = extract_reply_addressing(message.reply_to_message, bot_id=bot_id)
    return AddressingSignals(
        mentions_bot=message_mentions_bot(
            message,
            text,
            bot_id=bot_id,
            bot_username=bot_username,
        ),
        reply_to_bot=reply.reply_to_bot,
        reply_to_other_user=reply.reply_to_other_user,
        reply_to_sender_telegram_id=reply.reply_to_sender_telegram_id,
        reply_to_message_id=reply.reply_to_message_id,
        reply_to_text=reply.reply_to_text,
        reply_to_sender_name=reply.reply_to_sender_name,
    )
