"""Build a :class:`HermesClient` from settings (``None`` when Hermes is off)."""

from __future__ import annotations

from vanessa.infrastructure.hermes.client import HermesClient


def create_hermes_client(settings) -> HermesClient | None:
    if not (settings.hermes_enabled and settings.hermes_url):
        return None
    return HermesClient(
        settings.hermes_url,
        settings.hermes_api_key,
        timeout_seconds=settings.hermes_timeout_seconds,
    )


def hermes_session_id(channel: str, chat_id: int | str) -> str:
    """One Hermes session per chat."""
    return f"vanessa-{channel}-{chat_id}"
