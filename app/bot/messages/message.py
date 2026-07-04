from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.bot.addressing import extract_addressing
from aiogram import Bot
from aiogram.types import Message as TelegramMessage


def _enum_to_str(value: str | Enum) -> str:
    if isinstance(value, str):
        return value
    return value.value


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    telegram_chat_id: int
    telegram_message_id: int
    text: str
    sender_telegram_id: int
    chat_type: str
    bot: Bot = field(repr=False, compare=False)
    chat_title: str | None = None
    sender_username: str | None = None
    sender_first_name: str | None = None
    sender_last_name: str | None = None
    mentions_bot: bool = False
    reply_to_bot: bool = False
    reply_to_other_user: bool = False

    @classmethod
    def from_telegram(cls, message: TelegramMessage) -> "IncomingMessage":
        if message.from_user is None:
            raise ValueError("Сообщение без отправителя не поддерживается")
        addressing = extract_addressing(message)
        return cls(
            telegram_chat_id=message.chat.id,
            telegram_message_id=message.message_id,
            text=message.text or "",
            sender_telegram_id=message.from_user.id,
            chat_type=_enum_to_str(message.chat.type),
            bot=message.bot,
            chat_title=message.chat.title,
            sender_username=message.from_user.username,
            sender_first_name=message.from_user.first_name,
            sender_last_name=message.from_user.last_name,
            mentions_bot=addressing.mentions_bot,
            reply_to_bot=addressing.reply_to_bot,
            reply_to_other_user=addressing.reply_to_other_user,
        )

    def to_api_payload(self) -> dict[str, Any]:
        return {
            "telegram_chat_id": self.telegram_chat_id,
            "message": self.text,
            "sender_telegram_id": self.sender_telegram_id,
            "chat_title": self.chat_title,
            "chat_type": self.chat_type,
            "sender_username": self.sender_username,
            "sender_first_name": self.sender_first_name,
            "sender_last_name": self.sender_last_name,
            "mentions_bot": self.mentions_bot,
            "reply_to_bot": self.reply_to_bot,
            "reply_to_other_user": self.reply_to_other_user,
        }

    @property
    def is_text(self) -> bool:
        return bool(self.text.strip())
