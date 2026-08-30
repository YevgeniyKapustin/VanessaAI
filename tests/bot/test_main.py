from unittest.mock import AsyncMock, MagicMock

import pytest

from services.bot import main as bot_main


@pytest.mark.asyncio
async def test_main_starts_polling(monkeypatch):
    mock_bot = AsyncMock()
    mock_bot.get_me = AsyncMock(
        return_value=MagicMock(username="vanessa", id=1),
    )
    mock_router = MagicMock()
    mock_router.message.middleware = MagicMock()
    mock_dp = MagicMock()
    mock_dp.start_polling = AsyncMock()
    mock_dp.include_router = MagicMock()

    mock_services = MagicMock()
    mock_services.stickers = None

    monkeypatch.setattr(bot_main, "Bot", lambda token: mock_bot)
    monkeypatch.setattr(bot_main, "Dispatcher", lambda: mock_dp)
    monkeypatch.setattr(bot_main, "create_bot_services", lambda: mock_services)
    monkeypatch.setattr(bot_main, "create_router", lambda _: mock_router)

    await bot_main.main()

    mock_bot.get_me.assert_awaited_once()
    mock_dp.start_polling.assert_awaited_once_with(mock_bot)


@pytest.mark.asyncio
async def test_main_resolves_sticker_file_ids(monkeypatch):
    mock_bot = AsyncMock()
    mock_bot.get_me = AsyncMock(
        return_value=MagicMock(username="vanessa", id=1),
    )
    mock_router = MagicMock()
    mock_router.message.middleware = MagicMock()
    mock_dp = MagicMock()
    mock_dp.start_polling = AsyncMock()
    mock_dp.include_router = MagicMock()

    mock_stickers = MagicMock()
    mock_stickers.resolve_file_ids = AsyncMock()
    mock_services = MagicMock()
    mock_services.knowledge.ensure_structure = AsyncMock()
    mock_services.stickers = mock_stickers

    monkeypatch.setattr(bot_main, "Bot", lambda token: mock_bot)
    monkeypatch.setattr(bot_main, "Dispatcher", lambda: mock_dp)
    monkeypatch.setattr(bot_main, "create_bot_services", lambda: mock_services)
    monkeypatch.setattr(bot_main, "create_router", lambda _: mock_router)

    await bot_main.main()

    mock_stickers.resolve_file_ids.assert_awaited_once_with(mock_bot)
