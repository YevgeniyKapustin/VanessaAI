import pytest
from httpx import ASGITransport, AsyncClient

from services.mcp.runner import build_app
from vanessa.config import settings


@pytest.mark.asyncio
async def test_mcp_metrics_open_when_token_off(monkeypatch) -> None:
    monkeypatch.setattr(settings, "metrics_require_token", False)
    app = build_app("websearch")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        health = await client.get("/health")
        metrics = await client.get("/metrics")
    assert health.status_code == 200
    assert metrics.status_code == 200
    assert "text/plain" in metrics.headers["content-type"]


@pytest.mark.asyncio
async def test_mcp_metrics_requires_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "metrics_require_token", True)
    monkeypatch.setattr(settings, "api_internal_token", "secret")
    app = build_app("websearch")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        denied = await client.get("/metrics")
        allowed = await client.get(
            "/metrics",
            headers={"X-Internal-Token": "secret"},
        )
        bearer = await client.get(
            "/metrics",
            headers={"Authorization": "Bearer secret"},
        )
        health = await client.get("/health")
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert bearer.status_code == 200
    assert health.status_code == 200
