import pytest
import httpx

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
