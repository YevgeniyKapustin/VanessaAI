"""Owner names used to spot messages addressed to him in a group.

The single source is the People card of the owner (canonical name plus the
``aliases``/``telegram_username`` fields). ``PROXY_OWNER_ALIASES`` adds names
for a fresh install without a card.
"""

from __future__ import annotations

import re

from vanessa.config.owners import owner_telegram_ids
from vanessa.config.settings import settings
from vanessa.core.turn import ChatTurnInput
from vanessa.knowledge.users.nicknames import get_chat_aliases, get_telegram_nicknames


def _card_names() -> set[str]:
    names: set[str] = set()
    nicknames = get_telegram_nicknames()
    aliases = get_chat_aliases()
    for owner_id in owner_telegram_ids():
        canonical = nicknames.get(owner_id)
        if not canonical:
            continue
        names.add(canonical)
        names.update(aliases.get(canonical, ()))
    return names


def _configured_names() -> set[str]:
    return {
        raw.strip()
        for raw in settings.proxy_owner_aliases.split(",")
        if raw.strip()
    }


def owner_names() -> tuple[str, ...]:
    names = _card_names() | _configured_names()
    return tuple(sorted(names, key=len, reverse=True))


def owner_display_name() -> str:
    """The owner's canonical chat name (People card), else a neutral label."""
    nicknames = get_telegram_nicknames()
    for owner_id in owner_telegram_ids():
        canonical = nicknames.get(owner_id)
        if canonical:
            return canonical
    return "Evgeniy"


def name_hit(text: str, name: str) -> bool:
    value = name.casefold().strip()
    if not value:
        return False
    pattern = rf"(?<![\w@])@?{re.escape(value)}(?![\w])"
    return re.search(pattern, text) is not None


def addressed_to_owner(turn: ChatTurnInput) -> bool:
    """A reply to the owner's message or his name/@username in the text."""
    if turn.reply_to_sender_telegram_id in owner_telegram_ids():
        return True
    text = turn.message.casefold()
    return any(name_hit(text, name) for name in owner_names())
