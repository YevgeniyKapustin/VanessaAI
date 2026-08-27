import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_incoming_turn_handler
from app.api.main import app
from app.config import settings
from app.core.request_context import get_planning_started_signal
from app.core.turn import ChatTurnInput, ConversationTurnResult


class FakeHandler:
    def __init__(self) -> None:
        self.last_turn: ChatTurnInput | None = None

    async def handle_incoming(self, turn: ChatTurnInput) -> ConversationTurnResult:
        self.last_turn = turn
        return ConversationTurnResult(
            action="reply",
            reason="intent",
            reply="test reply",
            context_count=3,
            relevance_score=0.9,
        )


class FiringHandler(FakeHandler):
    """Handler that simulates the decision gate passing (fires the signal)."""

    async def handle_incoming(self, turn: ChatTurnInput) -> ConversationTurnResult:
        signal = get_planning_started_signal()
        if signal is not None:
            await signal()
        return await super().handle_incoming(turn)


_shared_handler = FakeHandler()


async def _override_handler() -> FakeHandler:
    return _shared_handler


@pytest.fixture
def api_client_override():
    app.dependency_overrides[get_incoming_turn_handler] = _override_handler
    yield
    app.dependency_overrides.clear()


def _parse_sse_events(body: str) -> dict[str, list[object]]:
    """Parse a raw SSE body into {event_name: [payloads]}."""
    events: dict[str, list[object]] = {}
    current: str | None = None
    data: list[str] = []
    for line in body.splitlines():
        if line == "":
            if current is not None:
                events.setdefault(current, []).append(json.loads("\n".join(data)))
            current = None
            data = []
        elif line.startswith("event:"):
            current = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:"):].strip())
    if current is not None:
        events.setdefault(current, []).append(json.loads("\n".join(data)))
    return events


async def _post_chat(client: AsyncClient, payload: dict, headers=None) -> str:
    async with client.stream(
        "POST",
        "/api/v1/chat",
        json=payload,
        headers=headers,
    ) as response:
        assert response.status_code == 200
        return "".join([chunk async for chunk in response.aiter_text()])


@pytest.mark.asyncio
async def test_chat_endpoint_returns_reply(api_client_override):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        body = await _post_chat(
            client,
            {
                "telegram_chat_id": -100123,
                "message": "hello",
                "sender_telegram_id": 42,
            },
        )

    events = _parse_sse_events(body)
    assert "result" in events
    data = events["result"][0]
    assert data["action"] == "reply"
    assert data["reply"] == "test reply"
    assert data["context_count"] == 3


@pytest.mark.asyncio
async def test_chat_endpoint_passes_reply_context(api_client_override):
    _shared_handler.last_turn = None
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await _post_chat(
            client,
            {
                "telegram_chat_id": -100123,
                "message": "а я про то и говорю",
                "sender_telegram_id": 42,
                "reply_to_message_id": 555,
                "reply_to_sender_telegram_id": 99,
                "reply_to_text": "Личь не делает карты",
                "reply_to_sender_name": "Личь",
            },
        )

    assert _shared_handler.last_turn is not None
    assert _shared_handler.last_turn.reply_to_message_id == 555
    assert _shared_handler.last_turn.reply_to_sender_telegram_id == 99
    assert _shared_handler.last_turn.reply_to_text == "Личь не делает карты"
    assert _shared_handler.last_turn.reply_to_sender_name == "Личь"


@pytest.mark.asyncio
async def test_chat_endpoint_returns_request_id(api_client_override):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        async with client.stream(
            "POST",
            "/api/v1/chat",
            json={
                "telegram_chat_id": -100123,
                "message": "hello",
                "sender_telegram_id": 42,
            },
            headers={"X-Request-ID": "trace-abc"},
        ) as response:
            assert response.headers["X-Request-ID"] == "trace-abc"
            async for _ in response.aiter_text():
                pass


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


@pytest.mark.asyncio
async def test_chat_endpoint_emits_started_when_gate_passes():
    firing_handler = FiringHandler()
    app.dependency_overrides[get_incoming_turn_handler] = lambda: firing_handler
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            body = await _post_chat(
                client,
                {
                    "telegram_chat_id": -100123,
                    "message": "hello",
                    "sender_telegram_id": 42,
                },
            )
    finally:
        app.dependency_overrides.clear()

    events = _parse_sse_events(body)
    assert list(events.keys()) == ["started", "result"]
    assert events["result"][0]["reply"] == "test reply"


@pytest.mark.asyncio
async def test_chat_endpoint_omits_started_when_gate_ignores():
    class IgnoringHandler(FakeHandler):
        async def handle_incoming(self, turn: ChatTurnInput) -> ConversationTurnResult:
            return ConversationTurnResult(
                action="ignore",
                reason="noise",
                reply=None,
                relevance_score=0.1,
            )

    app.dependency_overrides[get_incoming_turn_handler] = lambda: IgnoringHandler()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            body = await _post_chat(
                client,
                {
                    "telegram_chat_id": -100123,
                    "message": "hello",
                    "sender_telegram_id": 42,
                },
            )
    finally:
        app.dependency_overrides.clear()

    events = _parse_sse_events(body)
    assert list(events.keys()) == ["result"]
    assert events["result"][0]["action"] == "ignore"
