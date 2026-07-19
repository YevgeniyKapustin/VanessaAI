from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest

from app.bot.messages import IncomingMessage
from app.bot.messages.message import _enum_to_str
from app.config import settings
from app.config.content import get_content

GROUP_CHAT_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}
ACTIVE_MEMBER_STATUSES = {
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.RESTRICTED,
}


class ChatAccessGuard:
    def __init__(self, required_user_telegram_id: int | None = None) -> None:
        self._required_user_id = (
            required_user_telegram_id or settings.required_user_telegram_id
        )
        self._messages = get_content().bot.access

    def is_group_chat(self, message: IncomingMessage) -> bool:
        group_types = {_enum_to_str(chat_type) for chat_type in GROUP_CHAT_TYPES}
        return message.chat_type in group_types

    async def required_user_in_chat(self, message: IncomingMessage) -> bool:
        if not self._required_user_id:
            return False
        try:
            member = await message.bot.get_chat_member(
                chat_id=message.telegram_chat_id,
                user_id=self._required_user_id,
            )
        except TelegramBadRequest:
            return False
        return _enum_to_str(member.status) in {
            _enum_to_str(status) for status in ACTIVE_MEMBER_STATUSES
        }

    async def ensure_access(self, message: IncomingMessage) -> str | None:
        if not self.is_group_chat(message):
            return self._messages.private_chat.strip()
        if not self._required_user_id:
            return self._messages.required_user_not_configured.strip()
        if not await self.required_user_in_chat(message):
            return self._messages.required_user_missing.strip()
        return None

    def is_private_chat(self, message: IncomingMessage) -> bool:
        return message.chat_type == _enum_to_str(ChatType.PRIVATE)

    def ensure_owner_dm(self, message: IncomingMessage) -> str | None:
        notes = get_content().bot.notes
        if not self._required_user_id:
            return self._messages.required_user_not_configured.strip()
        if not self.is_private_chat(message):
            return notes.owner_dm_only.strip()
        if message.sender_telegram_id != self._required_user_id:
            return notes.owner_only.strip()
        return None
