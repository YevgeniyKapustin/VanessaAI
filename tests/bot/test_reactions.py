"""Reactions: recording what people react with, and putting one ourselves."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, MessageReactionUpdated, ReactionTypeEmoji, User

from services.bot.container import BotServices
from services.bot.handlers.message_process import _should_ignore
from services.bot.handlers.message_reaction import apply_reaction, has_other_output
from services.bot.handlers.messages import create_messages_router
from services.bot.handlers.reactions import (
    create_reactions_router,
    reaction_payload,
    record_reaction,
)
from services.bot.messages.response import ChatProcessResult
from tests.bot.test_bot_message import make_telegram_message
from vanessa.config.content import get_content

CHAT_ID = -100123
MESSAGE_ID = 77
USER_ID = 42


def _services(*, chat_allowed: bool = True) -> BotServices:
    chat_client = AsyncMock()
    chat_client.process = AsyncMock()
    chat_client.report_reaction = AsyncMock()
    access_guard = AsyncMock()
    access_guard.ensure_access = AsyncMock(return_value=None)
    access_guard.chat_allowed = MagicMock(return_value=chat_allowed)
    return BotServices(
        chat_client=chat_client,
        notes_client=AsyncMock(),
        access_guard=access_guard,
        texts=get_content().bot,
    )


def _update(*emojis: str, user: User | None = None) -> MessageReactionUpdated:
    return MessageReactionUpdated(
        chat=Chat(id=CHAT_ID, type="supergroup", title="Test chat"),
        message_id=MESSAGE_ID,
        date=datetime(2026, 10, 30, 12, 0, tzinfo=UTC),
        user=user
        or User(id=USER_ID, is_bot=False, first_name="Evgeniy", last_name="Kapustin"),
        old_reaction=[],
        new_reaction=[ReactionTypeEmoji(emoji=emoji) for emoji in emojis],
    )


def test_reaction_payload_carries_who_and_what():
    payload = reaction_payload(_update("🔥"))

    assert payload == {
        "telegram_chat_id": CHAT_ID,
        "chat_type": "supergroup",
        "message_id": MESSAGE_ID,
        "user_id": USER_ID,
        "user_name": "Evgeniy Kapustin",
        "emoji": "🔥",
    }


def test_reaction_removal_has_no_payload():
    update = _update()
    assert reaction_payload(update) is None


@pytest.mark.asyncio
async def test_record_reaction_forwards_the_task_payload():
    services = _services()

    await record_reaction(services, _update("❤"))

    services.chat_client.report_reaction.assert_awaited_once()
    payload = services.chat_client.report_reaction.await_args.args[0]
    assert payload["emoji"] == "❤"
    assert payload["message_id"] == MESSAGE_ID


@pytest.mark.asyncio
async def test_reaction_in_a_foreign_chat_is_ignored():
    services = _services(chat_allowed=False)

    await record_reaction(services, _update("❤"))

    services.chat_client.report_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_reaction_report_failure_is_swallowed():
    services = _services()
    services.chat_client.report_reaction = AsyncMock(side_effect=RuntimeError("redis"))

    await record_reaction(services, _update("❤"))

    services.chat_client.report_reaction.assert_awaited_once()


def test_reactions_router_registers_the_update():
    router = create_reactions_router(_services())
    assert router.message_reaction.handlers


@pytest.mark.asyncio
async def test_apply_reaction_sets_it_on_the_users_message():
    message = make_telegram_message()
    message.bot.set_message_reaction = AsyncMock(return_value=True)
    incoming = MagicMock(telegram_chat_id=CHAT_ID, telegram_message_id=MESSAGE_ID)
    result = ChatProcessResult(action="reply", reason="intent", reaction="🔥")

    applied = await apply_reaction(message, incoming, result)

    assert applied is True
    kwargs = message.bot.set_message_reaction.await_args.kwargs
    assert kwargs["chat_id"] == CHAT_ID
    assert kwargs["message_id"] == MESSAGE_ID
    assert kwargs["reaction"][0].emoji == "🔥"


@pytest.mark.asyncio
async def test_apply_reaction_failure_is_swallowed():
    message = make_telegram_message()
    message.bot.set_message_reaction = AsyncMock(side_effect=RuntimeError("no rights"))
    incoming = MagicMock(telegram_chat_id=CHAT_ID, telegram_message_id=MESSAGE_ID)

    applied = await apply_reaction(
        message, incoming, ChatProcessResult(action="reply", reason="intent", reaction="🔥")
    )

    assert applied is False


def test_reaction_only_turn_is_not_an_ignore():
    result = ChatProcessResult(action="reply", reason="intent", reaction="🔥")
    assert _should_ignore(result) is False
    assert has_other_output(result) is False


def test_reaction_with_text_keeps_the_text_output():
    result = ChatProcessResult(
        action="reply", reason="intent", reply="ага", reaction="🔥"
    )
    assert has_other_output(result) is True


def _text_handler(services: BotServices):
    router = create_messages_router(services)
    for handler in router.message.handlers:
        if getattr(handler.callback, "__name__", "") == "handle_text":
            return handler.callback
    raise AssertionError("handle_text not found")


@pytest.mark.asyncio
async def test_reaction_only_turn_sends_no_text():
    message = make_telegram_message()
    message.reply = AsyncMock()
    message.answer = AsyncMock()
    message.bot.set_message_reaction = AsyncMock(return_value=True)
    services = _services()
    services.chat_client.process = AsyncMock(
        return_value=ChatProcessResult(action="reply", reason="intent", reaction="🔥")
    )

    await _text_handler(services)(message)

    message.bot.set_message_reaction.assert_awaited_once()
    message.reply.assert_not_awaited()
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_reaction_with_a_reply_sends_both():
    message = make_telegram_message()
    message.reply = AsyncMock()
    message.bot.set_message_reaction = AsyncMock(return_value=True)
    services = _services()
    services.chat_client.process = AsyncMock(
        return_value=ChatProcessResult(
            action="reply", reason="intent", reply="ага", reaction="🔥"
        )
    )

    await _text_handler(services)(message)

    message.bot.set_message_reaction.assert_awaited_once()
    message.reply.assert_awaited_once()
