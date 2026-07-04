import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_turn_metrics
from app.api.main import app
from app.config import settings
from app.services.turn_metrics import TurnMetrics


@pytest.fixture
def metrics_client():
    metrics = TurnMetrics()
    app.dependency_overrides[get_turn_metrics] = lambda: metrics
    yield metrics
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_snapshot(metrics_client):
    metrics_client.record_turn(action="reply", reason="intent")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["replies"] == 1


@pytest.mark.asyncio
async def test_metrics_reset_clears_counters(metrics_client):
    metrics_client.record_turn(action="ignore", reason="noise")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        reset = await client.post("/api/v1/metrics/reset")
        snapshot = await client.get("/api/v1/metrics")
    assert reset.status_code == 200
    assert snapshot.json()["total"] == 0


@pytest.mark.asyncio
async def test_metrics_requires_token_when_configured(metrics_client, monkeypatch):
    monkeypatch.setattr(settings, "api_internal_token", "secret")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        denied = await client.get("/api/v1/metrics")
        allowed = await client.get(
            "/api/v1/metrics",
            headers={"X-Internal-Token": "secret"},
        )
    assert denied.status_code == 401
    assert allowed.status_code == 200
