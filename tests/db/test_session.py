from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db import session as db_session


@pytest.mark.asyncio
async def test_get_session_yields_and_closes(monkeypatch):
    mock_session = AsyncMock()
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=mock_context)
    monkeypatch.setattr(db_session, "async_session_factory", factory)

    gen = db_session.get_session()
    session = await gen.__anext__()

    assert session is mock_session
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
    mock_context.__aexit__.assert_awaited_once()
