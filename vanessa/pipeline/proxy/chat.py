"""Resolve the agents' chat where Vanessa answers for the owner."""

from __future__ import annotations

from dataclasses import dataclass

from vanessa.config.settings import settings
from vanessa.core.turn import ChatDestination


@dataclass(frozen=True, slots=True)
class ProxyChat:
    chat_id: int | None
    title: str | None


def _wanted_titles() -> tuple[str, ...]:
    return tuple(
        part.strip().casefold()
        for part in settings.proxy_chat_titles.split(",")
        if part.strip()
    )


def title_matches(title: str | None) -> bool:
    if not title:
        return False
    folded = title.casefold()
    return any(part in folded for part in _wanted_titles())


def current_proxy_chat(
    chat_title: str | None,
    telegram_chat_id: int | None,
) -> ProxyChat | None:
    """The chat of this turn when it is the agents' chat, else None."""
    pinned = settings.proxy_chat_telegram_id
    if pinned:
        if telegram_chat_id == pinned:
            return ProxyChat(pinned, chat_title)
        return None
    if title_matches(chat_title):
        return ProxyChat(telegram_chat_id, chat_title)
    return None


def find_proxy_chat(
    known_chats: tuple[ChatDestination, ...],
) -> ProxyChat | None:
    """The agents' chat in the known-chat directory (used from a DM)."""
    pinned = settings.proxy_chat_telegram_id
    if pinned:
        match = next((chat for chat in known_chats if chat.chat_id == pinned), None)
        return ProxyChat(pinned, match.title if match else None)
    for chat in known_chats:
        if title_matches(chat.title):
            return ProxyChat(chat.chat_id, chat.title)
    return None
