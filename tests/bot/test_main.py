import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.bot import main as bot_main


@pytest.fixture(autouse=True)
def _stub_metrics_http_server(monkeypatch):
    monkeypatch.setattr(
        "vanessa.infrastructure.observability.metrics.start_metrics_http_server",
        lambda _port, _addr="0.0.0.0": MagicMock(),
    )


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
    mock_services.streams = None

    def _bot(token):
        _ = token
        return mock_bot

    monkeypatch.setattr(bot_main, "Bot", _bot)
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
    mock_services.streams = None

    def _bot(token):
        _ = token
        return mock_bot

    monkeypatch.setattr(bot_main, "Bot", _bot)
    monkeypatch.setattr(bot_main, "Dispatcher", lambda: mock_dp)
    monkeypatch.setattr(bot_main, "create_bot_services", lambda: mock_services)
    monkeypatch.setattr(bot_main, "create_router", lambda _: mock_router)

    await bot_main.main()

    mock_stickers.resolve_file_ids.assert_awaited_once_with(mock_bot)



class _FakeOutboundLoop:
    def __init__(self) -> None:
        self.args: tuple | None = None
        self.cancelled = False

    def start(self, broker, streams, bot) -> asyncio.Task:
        self.args = (broker, streams, bot)
        return asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


async def _yield_polling(_bot) -> None:
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_main_starts_and_cancels_outbound_task(monkeypatch):
    mock_bot = AsyncMock()
    mock_bot.get_me = AsyncMock(return_value=MagicMock(username="vanessa", id=1))
    mock_dp = MagicMock()
    mock_dp.start_polling = _yield_polling
    mock_services = MagicMock()
    mock_services.stickers = None
    outbound = _FakeOutboundLoop()

    monkeypatch.setattr(bot_main, "Bot", lambda **_kwargs: mock_bot)
    monkeypatch.setattr(bot_main, "Dispatcher", lambda: mock_dp)
    monkeypatch.setattr(bot_main, "create_bot_services", lambda: mock_services)
    monkeypatch.setattr(bot_main, "create_router", lambda _: MagicMock())
    monkeypatch.setattr(bot_main, "start_outbound_task", outbound.start)

    await bot_main.main()

    assert outbound.args == (mock_services.broker, mock_services.streams, mock_bot)
    assert outbound.cancelled is True
