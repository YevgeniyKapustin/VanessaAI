from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TelegramUserProfile:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None


async def fetch_telegram_user(
    telegram_id: int,
    bot_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> TelegramUserProfile | None:
    if not bot_token:
        return None

    url = f"https://api.telegram.org/bot{bot_token}/getChat"
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=15.0)

    try:
        response = await client.get(url, params={"chat_id": telegram_id})
        payload = response.json()
        if not payload.get("ok"):
            logger.debug(
                "getChat failed telegram_id=%s error=%s",
                telegram_id,
                payload.get("description"),
            )
            return None
        chat = payload["result"]
        return TelegramUserProfile(
            telegram_id=telegram_id,
            username=chat.get("username"),
            first_name=chat.get("first_name"),
            last_name=chat.get("last_name"),
        )
    except httpx.HTTPError as exc:
        logger.warning("getChat request failed telegram_id=%s error=%s", telegram_id, exc)
        return None
    finally:
        if owns_client:
            await client.aclose()


async def fetch_telegram_users(
    telegram_ids: list[int],
    bot_token: str,
    *,
    delay_seconds: float = 0.05,
) -> dict[int, TelegramUserProfile]:
    profiles: dict[int, TelegramUserProfile] = {}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for index, telegram_id in enumerate(telegram_ids):
            profile = await fetch_telegram_user(
                telegram_id,
                bot_token,
                client=client,
            )
            if profile is not None:
                profiles[telegram_id] = profile
            if delay_seconds > 0 and index + 1 < len(telegram_ids):
                await asyncio.sleep(delay_seconds)
    return profiles
