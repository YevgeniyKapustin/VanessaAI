from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app, lifespan


@pytest.mark.asyncio
async def test_lifespan_runs_startup_and_shutdown(monkeypatch):
    mock_conn = AsyncMock()
    mock_conn.run_sync = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.begin = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    mock_engine.dispose = AsyncMock()
    monkeypatch.setattr("app.api.main.engine", mock_engine)
    monkeypatch.setattr("app.api.main.settings.api_auto_create_schema", True)

    vector_store = AsyncMock()
    vector_store.ensure_collection = AsyncMock()
    monkeypatch.setattr(
        "app.api.main.create_vector_store",
        lambda: vector_store,
    )

    embeddings = AsyncMock()
    embeddings.embed = AsyncMock(return_value=[0.1])
    monkeypatch.setattr(
        "app.api.main.create_embedding_provider",
        lambda: embeddings,
    )
    monkeypatch.setattr("app.api.main.preload_embedding_model", lambda: None)

    async with lifespan(app):
        vector_store.ensure_collection.assert_awaited_once()
        embeddings.embed.assert_awaited_once_with("warmup")

    mock_engine.dispose.assert_awaited_once()
    mock_conn.run_sync.assert_awaited_once()


@pytest.mark.asyncio
async def test_app_health_after_lifespan_mocks(monkeypatch):
    mock_engine = MagicMock()
    mock_engine.begin = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=AsyncMock(run_sync=AsyncMock())),
        __aexit__=AsyncMock(return_value=None),
    ))
    mock_engine.dispose = AsyncMock()
    monkeypatch.setattr("app.api.main.engine", mock_engine)
    monkeypatch.setattr("app.api.main.settings.api_auto_create_schema", False)

    vector_store = AsyncMock()
    vector_store.ensure_collection = AsyncMock()
    embeddings = AsyncMock()
    embeddings.embed = AsyncMock(return_value=[0.1])
    monkeypatch.setattr("app.api.main.create_vector_store", lambda: vector_store)
    monkeypatch.setattr(
        "app.api.main.create_embedding_provider",
        lambda: embeddings,
    )
    monkeypatch.setattr("app.api.main.preload_embedding_model", lambda: None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
