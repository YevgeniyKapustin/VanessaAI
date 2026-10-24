"""Adapter side of bot-to-bot talk: flags, labels and the owner guard."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ChatMemberStatus, ChatType

from services.agent.broker_worker.mapping import TurnMapper
from services.bot.addressing_reply import extract_reply_addressing
from services.bot.handlers.message_delivery import _reject_if_no_access
from services.bot.messages import IncomingMessage
from services.bot.outbound import handle_outbound
from services.bot.outbound.gate import owner_allows
from services.bot.services.chat_access import ChatAccessGuard
from vanessa.config.settings import settings
from vanessa.contracts import OutboundMessage, TurnRequest
from vanessa.infrastructure.broker.backends import Delivery

OWNER = 999
VANESSA = 1000
KIRILL = 777
GROUP = -100123


def _telegram_message(*, is_bot: bool) -> MagicMock:
    message = MagicMock()
    message.chat.id = GROUP
    message.chat.type = ChatType.GROUP
    message.chat.title = "Test chat"
    message.message_id = 99
    message.text = "Ванесса, привет"
    message.from_user.id = KIRILL
    message.from_user.username = "kirill_ai_bot"
    message.from_user.first_name = "Kirill"
    message.from_user.last_name = None
    message.from_user.is_bot = is_bot
    message.reply_to_message = None
    message.entities = None
    message.bot = MagicMock()
    return message


def test_bot_flag_flows_from_telegram_to_turn():
    incoming = IncomingMessage.from_telegram(_telegram_message(is_bot=True))
    assert incoming.sender_is_bot is True
    assert incoming.to_api_payload()["sender_is_bot"] is True
    request = TurnRequest(message="hi", sender_is_bot=True)
    assert TurnMapper().to_turn(request).sender_is_bot is True
    human = IncomingMessage.from_telegram(_telegram_message(is_bot=False))
    assert human.sender_is_bot is False


def _author(user_id: int, *, is_bot: bool):
    return SimpleNamespace(
        id=user_id, is_bot=is_bot, first_name="Kirill", last_name=None, username="k"
    )


def test_reply_to_other_bot_is_labelled_but_own_bot_is_not():
    other = SimpleNamespace(
        from_user=_author(KIRILL, is_bot=True), message_id=5, text="t"
    )
    own = SimpleNamespace(from_user=_author(VANESSA, is_bot=True), message_id=6, text="t")
    assert (
        extract_reply_addressing(other, bot_id=VANESSA).reply_to_sender_name
        == "[бот Kirill]"
    )
    assert extract_reply_addressing(own, bot_id=VANESSA).reply_to_sender_name == "Kirill"


def _incoming(*, is_bot: bool) -> IncomingMessage:
    return IncomingMessage(
        telegram_chat_id=GROUP,
        telegram_message_id=1,
        text="Ванесса?",
        sender_telegram_id=KIRILL,
        chat_type=ChatType.GROUP.value,
        bot=MagicMock(),
        sender_is_bot=is_bot,
        mentions_bot=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("is_bot", "answers"), [(True, 0), (False, 1)])
async def test_denial_text_never_goes_to_a_bot(is_bot, answers):
    services = MagicMock()
    services.access_guard.ensure_access = AsyncMock(return_value="no access")
    services.access_guard.is_private_chat = MagicMock(return_value=False)
    telegram_message = MagicMock()
    telegram_message.answer = AsyncMock()

    assert await _reject_if_no_access(services, telegram_message, _incoming(is_bot=is_bot))
    assert telegram_message.answer.await_count == answers


def _bot_api(present: set[int]) -> AsyncMock:
    async def member(chat_id, user_id):
        _ = chat_id
        status = ChatMemberStatus.MEMBER if user_id in present else ChatMemberStatus.LEFT
        return MagicMock(status=status)

    bot = AsyncMock()
    bot.get_chat_member = AsyncMock(side_effect=member)
    bot.send_message = AsyncMock()
    return bot


@pytest.mark.asyncio
async def test_owner_guard_checks_chat_membership(monkeypatch):
    monkeypatch.setattr(settings, "required_user_telegram_id", OWNER)
    monkeypatch.setattr(settings, "owner_extra_telegram_ids", "")
    guard = ChatAccessGuard(required_user_telegram_id=OWNER)
    assert await owner_allows(guard, _bot_api({OWNER}), GROUP)
    assert not await owner_allows(guard, _bot_api(set()), GROUP)
    assert await owner_allows(guard, _bot_api(set()), OWNER)
    assert not await owner_allows(guard, _bot_api({OWNER}), None)
    assert await owner_allows(None, _bot_api(set()), GROUP)
    broken = MagicMock()
    broken.owner_in_chat = AsyncMock(side_effect=RuntimeError("api down"))
    assert not await owner_allows(broken, _bot_api({OWNER}), GROUP)


@pytest.mark.asyncio
async def test_follow_up_to_chat_without_owner_is_dropped(monkeypatch):
    monkeypatch.setattr(settings, "required_user_telegram_id", OWNER)
    monkeypatch.setattr(settings, "owner_extra_telegram_ids", "")
    guard = ChatAccessGuard(required_user_telegram_id=OWNER)
    bot = _bot_api(set())
    message = OutboundMessage(telegram_chat_id=GROUP, text="done", source="hermes")
    delivery = Delivery(stream="s", stream_id="1-0", message=message)

    await handle_outbound(bot, delivery, access_guard=guard)

    bot.send_message.assert_not_awaited()
