from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from services.agent.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_liveness_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_endpoint_ready():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    engine_mock = MagicMock()
    engine_mock.connect.return_value.__aenter__ = AsyncMock(return_value=conn)
    engine_mock.connect.return_value.__aexit__ = AsyncMock(return_value=None)
    with patch("services.agent.routes.health.engine", engine_mock):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_readiness_endpoint_unavailable():
    engine_mock = MagicMock()
    engine_mock.connect.side_effect = RuntimeError("db down")
    with patch("services.agent.routes.health.engine", engine_mock):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


@pytest.mark.asyncio
async def test_chat_http_endpoint_removed():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/chat",
            json={
                "telegram_chat_id": 1,
                "message": "hi",
                "sender_telegram_id": 2,
            },
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_notes_http_endpoint_removed():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/notes",
            json={"text": "hi"},
        )
    assert response.status_code == 404
