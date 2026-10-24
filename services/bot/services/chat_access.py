from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest

from services.bot.messages import IncomingMessage
from services.bot.messages.message import _enum_to_str
from vanessa.config import settings
from vanessa.config.content import get_content
from vanessa.config.owners import is_owner, owner_telegram_ids

GROUP_CHAT_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}
ACTIVE_MEMBER_STATUSES = {
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.RESTRICTED,
}


class ChatAccessGuard:
    def __init__(
        self,
        required_user_telegram_id: int | None = None,
        allowed_chat_telegram_id: int | None = None,
    ) -> None:
        self._required_user_id = (
            required_user_telegram_id or settings.required_user_telegram_id
        )
        self._allowed_chat_id = (
            allowed_chat_telegram_id or settings.allowed_chat_telegram_id
        )
        self._messages = get_content().bot.access

    def is_group_chat(self, message: IncomingMessage) -> bool:
        group_types = {_enum_to_str(chat_type) for chat_type in GROUP_CHAT_TYPES}
        return message.chat_type in group_types

    def _owner_ids(self) -> list[int]:
        extra = owner_telegram_ids() - {self._required_user_id}
        return [self._required_user_id, *sorted(extra)]

    async def required_user_in_chat(self, message: IncomingMessage) -> bool:
        return await self.owner_in_chat(message.bot, message.telegram_chat_id)

    async def owner_in_chat(self, bot, chat_id: int) -> bool:
        """Whether the owner (or a co-owner) is an active member of ``chat_id``."""
        if not self._required_user_id:
            return False
        for user_id in self._owner_ids():
            if await _is_active_member(bot, chat_id, user_id):
                return True
        return False

    async def ensure_access(self, message: IncomingMessage) -> str | None:
        denial = self._static_access_denial(message)
        if denial:
            return denial
        if not await self.required_user_in_chat(message):
            return self._messages.required_user_missing.strip()
        return None

    def _static_access_denial(self, message: IncomingMessage) -> str | None:
        wrong = self._wrong_chat(message)
        if wrong:
            return wrong
        if not self.is_group_chat(message):
            return self._messages.private_chat.strip()
        if not self._required_user_id:
            return self._messages.required_user_not_configured.strip()
        return None

    def _wrong_chat(self, message: IncomingMessage) -> str | None:
        if not self._allowed_chat_id:
            return None
        if message.telegram_chat_id != self._allowed_chat_id:
            return self._messages.wrong_chat.strip()
        return None

    def is_private_chat(self, message: IncomingMessage) -> bool:
        return message.chat_type == _enum_to_str(ChatType.PRIVATE)

    def ensure_owner_dm(self, message: IncomingMessage) -> str | None:
        notes = get_content().bot.notes
        if not self._required_user_id:
            return self._messages.required_user_not_configured.strip()
        if not self.is_private_chat(message):
            return notes.owner_dm_only.strip()
        sender = message.sender_telegram_id
        if sender != self._required_user_id and not is_owner(sender):
            return notes.owner_only.strip()
        return None


async def _is_active_member(bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramBadRequest:
        return False
    return _enum_to_str(member.status) in {
        _enum_to_str(status) for status in ACTIVE_MEMBER_STATUSES
    }
