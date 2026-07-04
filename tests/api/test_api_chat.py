import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_incoming_turn_handler
from app.api.main import app
from app.config import settings
from app.core.turn import ChatTurnInput, ConversationTurnResult


class FakeHandler:
    async def handle_incoming(self, turn: ChatTurnInput) -> ConversationTurnResult:
        return ConversationTurnResult(
            action="reply",
            reason="intent",
            reply="test reply",
            context_count=3,
            relevance_score=0.9,
        )


async def _override_handler() -> FakeHandler:
    return FakeHandler()


@pytest.fixture
def api_client_override():
    app.dependency_overrides[get_incoming_turn_handler] = _override_handler
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_endpoint_returns_reply(api_client_override):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/chat",
            json={
                "telegram_chat_id": -100123,
                "message": "hello",
                "sender_telegram_id": 42,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "reply"
    assert data["reply"] == "test reply"
    assert data["context_count"] == 3


@pytest.mark.asyncio
async def test_chat_endpoint_returns_request_id(api_client_override):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/chat",
            json={
                "telegram_chat_id": -100123,
                "message": "hello",
                "sender_telegram_id": 42,
            },
            headers={"X-Request-ID": "trace-abc"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-abc"


@pytest.mark.asyncio
async def test_chat_endpoint_rejects_invalid_token(api_client_override, monkeypatch):
    monkeypatch.setattr(settings, "api_internal_token", "secret")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        denied = await client.post(
            "/api/v1/chat",
            json={
                "telegram_chat_id": -100123,
                "message": "hello",
                "sender_telegram_id": 42,
            },
        )
        allowed = await client.post(
            "/api/v1/chat",
            json={
                "telegram_chat_id": -100123,
                "message": "hello",
                "sender_telegram_id": 42,
            },
            headers={"X-Internal-Token": "secret"},
        )

    assert denied.status_code == 401
    assert allowed.status_code == 200
