import pytest
from httpx import ASGITransport, AsyncClient

from services.agent_core.main import app
from vanessa.config import settings
from vanessa.observability.metrics import record_turn


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "metrics_require_token", False)
    record_turn("reply", "intent")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "vanessa_turns_total" in response.text


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint_requires_token_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "metrics_require_token", True)
    monkeypatch.setattr(settings, "api_internal_token", "secret")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        denied = await client.get("/metrics")
        allowed = await client.get("/metrics", headers={"X-Internal-Token": "secret"})
    assert denied.status_code == 401
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_json_snapshot_route_still_intact():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/metrics")
    assert response.status_code == 200
    assert "total" in response.json()
