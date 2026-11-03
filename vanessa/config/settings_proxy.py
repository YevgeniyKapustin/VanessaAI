"""Proxy mode: Vanessa answers agents for the owner and can DM him.

Off by default. ``PROXY_CHAT_TELEGRAM_ID`` pins the agents' group; without it
the chat is matched by title from ``PROXY_CHAT_TITLES``.
"""

from __future__ import annotations


class ProxyMixin:
    """Settings for the agents' chat and the owner's private chat."""

    # Telegram id of the group where Vanessa speaks for the owner. 0 = by title.
    proxy_chat_telegram_id: int = 0
    # Comma-separated case-insensitive chat titles that mark the agents' chat.
    proxy_chat_titles: str = "agents,агенты"
    # Extra names for the owner besides the People card (comma-separated).
    proxy_owner_aliases: str = ""
    # Owner may talk to Vanessa in a private chat (DM).
    owner_dm_enabled: bool = True
