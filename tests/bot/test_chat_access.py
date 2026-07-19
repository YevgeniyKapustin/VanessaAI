from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ChatMemberStatus, ChatType

from app.bot.messages import IncomingMessage
from app.bot.services.chat_access import ChatAccessGuard
from app.config.content import get_content


def make_incoming(
    chat_type: ChatType = ChatType.GROUP,
    chat_id: int = -100123,
    user_in_chat: bool = True,
) -> IncomingMessage:
    bot = AsyncMock()
    member = MagicMock()
    member.status = ChatMemberStatus.MEMBER if user_in_chat else ChatMemberStatus.LEFT
    bot.get_chat_member = AsyncMock(return_value=member)
    return IncomingMessage(
        telegram_chat_id=chat_id,
        telegram_message_id=1,
        text="Привет",
        sender_telegram_id=42,
        chat_type=chat_type.value,
        bot=bot,
        chat_title="Test chat",
    )


@pytest.mark.asyncio
async def test_private_chat_rejected():
    guard = ChatAccessGuard(required_user_telegram_id=999)
    incoming = make_incoming(chat_type=ChatType.PRIVATE)
    texts = get_content().bot.access

    error = await guard.ensure_access(incoming)

    assert error == texts.private_chat.strip()


@pytest.mark.asyncio
async def test_group_without_required_user_rejected():
    guard = ChatAccessGuard(required_user_telegram_id=999)
    incoming = make_incoming(user_in_chat=False)
    texts = get_content().bot.access

    error = await guard.ensure_access(incoming)

    assert error == texts.required_user_missing.strip()


@pytest.mark.asyncio
async def test_group_with_required_user_allowed():
    guard = ChatAccessGuard(required_user_telegram_id=999)
    incoming = make_incoming(user_in_chat=True)

    error = await guard.ensure_access(incoming)

    assert error is None


def test_owner_dm_allowed():
    guard = ChatAccessGuard(required_user_telegram_id=42)
    incoming = make_incoming(chat_type=ChatType.PRIVATE)

    error = guard.ensure_owner_dm(incoming)

    assert error is None


def test_owner_dm_rejects_group():
    guard = ChatAccessGuard(required_user_telegram_id=42)
    incoming = make_incoming(chat_type=ChatType.GROUP)
    texts = get_content().bot.notes

    error = guard.ensure_owner_dm(incoming)

    assert error == texts.owner_dm_only.strip()


def test_owner_dm_rejects_other_user():
    guard = ChatAccessGuard(required_user_telegram_id=999)
    incoming = make_incoming(chat_type=ChatType.PRIVATE)
    texts = get_content().bot.notes

    error = guard.ensure_owner_dm(incoming)

    assert error == texts.owner_only.strip()
