import pytest
import httpx
from unittest.mock import AsyncMock

from app.ingest.telegram_users import fetch_telegram_user


@pytest.mark.asyncio
async def test_fetch_telegram_user_parses_profile():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["chat_id"] == "123"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "id": 123,
                    "username": "alice",
                    "first_name": "Alice",
                    "last_name": "Smith",
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        profile = await fetch_telegram_user(123, "token", client=client)

    assert profile is not None
    assert profile.telegram_id == 123
    assert profile.username == "alice"
    assert profile.first_name == "Alice"
    assert profile.last_name == "Smith"


@pytest.mark.asyncio
async def test_fetch_telegram_user_returns_none_on_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "description": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        profile = await fetch_telegram_user(999, "token", client=client)

    assert profile is None


@pytest.mark.asyncio
async def test_fetch_telegram_user_empty_token():
    assert await fetch_telegram_user(1, "") is None


@pytest.mark.asyncio
async def test_fetch_telegram_user_handles_http_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        profile = await fetch_telegram_user(1, "token", client=client)

    assert profile is None


@pytest.mark.asyncio
async def test_fetch_telegram_users_batch(monkeypatch):
    from app.ingest.telegram_users import fetch_telegram_users

    calls: list[int] = []

    async def fake_fetch(
        telegram_id: int,
        bot_token: str,
        *,
        client: httpx.AsyncClient | None = None,
    ):
        calls.append(telegram_id)
        return type(
            "Profile",
            (),
            {
                "telegram_id": telegram_id,
                "username": f"u{telegram_id}",
                "first_name": None,
                "last_name": None,
            },
        )()

    monkeypatch.setattr(
        "app.ingest.telegram_users.fetch_telegram_user",
        fake_fetch,
    )
    monkeypatch.setattr("app.ingest.telegram_users.asyncio.sleep", AsyncMock())

    profiles = await fetch_telegram_users([1, 2], "token", delay_seconds=0.01)

    assert calls == [1, 2]
    assert profiles[1].username == "u1"
    assert profiles[2].username == "u2"
