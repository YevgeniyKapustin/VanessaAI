from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app


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
    with patch("app.api.routes.health.engine", engine_mock):
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
    with patch("app.api.routes.health.engine", engine_mock):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
