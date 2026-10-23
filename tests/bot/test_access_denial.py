from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ChatMemberStatus, ChatType

from services.bot.handlers.message_delivery import _reject_if_no_access
from services.bot.messages import IncomingMessage
from services.bot.services.chat_access import ChatAccessGuard
from vanessa.config import owners
from vanessa.config.content import get_content
from vanessa.config.settings import settings

OWNER = 999
SECOND_OWNER = 777


@pytest.fixture
def two_owners(monkeypatch):
    monkeypatch.setattr(settings, "required_user_telegram_id", OWNER)
    monkeypatch.setattr(settings, "owner_extra_telegram_ids", f" {SECOND_OWNER}, x,")


def _incoming(
    *,
    chat_type: ChatType = ChatType.GROUP,
    sender: int = 42,
    mentions_bot: bool = False,
    reply_to_bot: bool = False,
    present: frozenset[int] = frozenset(),
) -> IncomingMessage:
    async def member(chat_id, user_id):
        status = ChatMemberStatus.MEMBER if user_id in present else ChatMemberStatus.LEFT
        return MagicMock(status=status)

    bot = AsyncMock()
    bot.get_chat_member = AsyncMock(side_effect=member)
    return IncomingMessage(
        telegram_chat_id=-100123,
        telegram_message_id=1,
        text="Привет",
        sender_telegram_id=sender,
        chat_type=chat_type.value,
        bot=bot,
        mentions_bot=mentions_bot,
        reply_to_bot=reply_to_bot,
    )


def test_owner_ids_parse_extra_accounts(two_owners):
    assert owners.owner_telegram_ids() == {OWNER, SECOND_OWNER}
    assert owners.is_owner(SECOND_OWNER)
    assert not owners.is_owner(42)
    assert not owners.is_owner(None)
    assert owners.owner_id_for(SECOND_OWNER) == SECOND_OWNER
    assert owners.owner_id_for(42) == OWNER


@pytest.mark.asyncio
async def test_second_owner_account_grants_access(two_owners):
    guard = ChatAccessGuard()
    incoming = _incoming(present=frozenset({SECOND_OWNER}))

    assert await guard.ensure_access(incoming) is None


@pytest.mark.asyncio
async def test_no_owner_account_in_chat_denied(two_owners):
    guard = ChatAccessGuard()
    texts = get_content().bot.access

    error = await guard.ensure_access(_incoming())

    assert error == texts.required_user_missing.strip()


def test_second_owner_account_passes_owner_dm(two_owners):
    guard = ChatAccessGuard()
    incoming = _incoming(chat_type=ChatType.PRIVATE, sender=SECOND_OWNER)

    assert guard.ensure_owner_dm(incoming) is None


def _services(error: str | None) -> MagicMock:
    services = MagicMock()
    services.access_guard = ChatAccessGuard(required_user_telegram_id=OWNER)
    services.access_guard.ensure_access = AsyncMock(return_value=error)
    return services


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("incoming", "answered"),
    [
        (_incoming(), False),
        (_incoming(mentions_bot=True), True),
        (_incoming(reply_to_bot=True), True),
        (_incoming(chat_type=ChatType.PRIVATE), True),
    ],
)
async def test_denial_text_only_when_addressed(incoming, answered):
    telegram_message = MagicMock()
    telegram_message.answer = AsyncMock()

    rejected = await _reject_if_no_access(_services("no access"), telegram_message, incoming)

    assert rejected is True
    assert telegram_message.answer.await_count == int(answered)


@pytest.mark.asyncio
async def test_access_granted_sends_nothing():
    telegram_message = MagicMock()
    telegram_message.answer = AsyncMock()

    rejected = await _reject_if_no_access(_services(None), telegram_message, _incoming())

    assert rejected is False
    telegram_message.answer.assert_not_awaited()
