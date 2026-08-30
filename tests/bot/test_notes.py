from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from aiogram.enums import ChatType
from aiogram.filters import CommandObject

from services.bot.container import BotServices
from services.bot.handlers.notes import create_notes_router
from tests.bot.test_bot_message import make_telegram_message
from vanessa.config.content import get_content


@pytest.mark.asyncio
async def test_cmd_note_rejects_non_owner_dm():
    message = make_telegram_message(text="/note hi", chat_type=ChatType.PRIVATE)
    message.answer = AsyncMock()
    message.photo = None
    access_guard = MagicMock()
    access_guard.ensure_owner_dm = MagicMock(
        return_value=get_content().bot.notes.owner_only.strip()
    )
    services = BotServices(
        chat_client=AsyncMock(),
        notes_client=AsyncMock(),
        access_guard=access_guard,
        texts=get_content().bot,
    )
    router = create_notes_router(services)
    handler = router.message.handlers[0].callback
    await handler(message, CommandObject(prefix="/", command="note", args="hi"))

    message.answer.assert_awaited_once_with(
        get_content().bot.notes.owner_only.strip()
    )


@pytest.mark.asyncio
async def test_cmd_note_saves_via_agent_core_for_owner():
    message = make_telegram_message(text="/note buy milk", chat_type=ChatType.PRIVATE)
    message.from_user.id = 42
    message.answer = AsyncMock()
    message.photo = None
    access_guard = MagicMock()
    access_guard.ensure_owner_dm = MagicMock(return_value=None)
    notes_client = AsyncMock()
    notes_client.save_inbox_note = AsyncMock(return_value="inbox/2026-08-26_000000.md")
    services = BotServices(
        chat_client=AsyncMock(),
        notes_client=notes_client,
        access_guard=access_guard,
        texts=get_content().bot,
    )
    router = create_notes_router(services)
    handler = router.message.handlers[0].callback
    await handler(
        message,
        CommandObject(prefix="/", command="note", args="buy milk"),
    )

    notes_client.save_inbox_note.assert_awaited_once()
    kwargs = notes_client.save_inbox_note.await_args.kwargs
    assert kwargs["text"] == "buy milk"
    assert "inbox/" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_cmd_note_maps_503_to_not_configured():
    message = make_telegram_message(text="/note hi", chat_type=ChatType.PRIVATE)
    message.answer = AsyncMock()
    message.photo = None
    access_guard = MagicMock()
    access_guard.ensure_owner_dm = MagicMock(return_value=None)
    request = httpx.Request("POST", "http://api/api/v1/notes")
    response = httpx.Response(503, request=request)
    notes_client = AsyncMock()
    notes_client.save_inbox_note = AsyncMock(
        side_effect=httpx.HTTPStatusError("no", request=request, response=response)
    )
    services = BotServices(
        chat_client=AsyncMock(),
        notes_client=notes_client,
        access_guard=access_guard,
        texts=get_content().bot,
    )
    router = create_notes_router(services)
    handler = router.message.handlers[0].callback
    await handler(message, CommandObject(prefix="/", command="note", args="hi"))
    message.answer.assert_awaited_once_with(
        get_content().bot.notes.not_configured.strip()
    )
