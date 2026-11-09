"""Parse the composer's ``[reaction:<emoji>]`` marker.

Vanessa may answer a message with just an emoji reaction (Telegram
``setMessageReaction``) — a laugh, a like, sympathy — instead of a full reply.
The marker is stripped from the text exactly like the sticker tag: code blocks
are left untouched, at most one reaction survives, and an emoji Telegram does
not accept is dropped (never passed to the API, where it would raise).
"""

import logging
import re

from vanessa.core.text.code_fences import (
    map_outside_fences as _map_outside_fences,
)

logger = logging.getLogger(__name__)

#: Emoji Telegram accepts as a standard message reaction.
TELEGRAM_REACTION_EMOJI = (
    "👍", "👎", "❤", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱",
    "🤬", "😢", "🎉", "🤩", "🤮", "💩", "🙏", "👌", "🕊", "🤡",
    "🥱", "🥴", "😍", "🐳", "❤‍🔥", "🌚", "🌭", "💯", "🤣", "⚡",
    "🍌", "🏆", "💔", "🤨", "😐", "🍓", "🍾", "💋", "😈", "😴",
    "😭", "🤓", "👻", "👀", "🎃", "🙈", "😇", "😨", "🤝", "✍",
    "🤗", "🫡", "🥹", "🤪", "😎",
)

_VARIATION_SELECTOR = "\ufe0f"

_MARKER = re.compile(
    r"\[(?:reaction|реакция)\s*:\s*([^\[\]\n]{1,16}?)\s*\]",
    re.IGNORECASE,
)


def _normalize(emoji: str) -> str:
    return emoji.replace(_VARIATION_SELECTOR, "").strip()


_ALLOWED = frozenset(_normalize(emoji) for emoji in TELEGRAM_REACTION_EMOJI)


def is_allowed_reaction(emoji: str) -> bool:
    """Whether Telegram accepts ``emoji`` as a standard reaction."""
    return bool(emoji) and _normalize(emoji) in _ALLOWED


def _strip_markers(segment: str, found: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        candidate = match.group(1).strip()
        if not found and is_allowed_reaction(candidate):
            found.append(_normalize(candidate))
        else:
            logger.info("reaction_marker_dropped emoji=%r", candidate)
        return ""

    return _MARKER.sub(replace, segment)


def extract_reaction(reply: str) -> tuple[str, str | None]:
    """Strip the composer's reaction marker out of a reply.

    Returns ``(clean_reply, emoji_or_None)``. Only the first valid emoji is
    kept; unknown emoji are dropped so the Telegram API never rejects them.
    """
    if not reply:
        return reply, None
    found: list[str] = []
    result = _map_outside_fences(
        reply, lambda segment: _strip_markers(segment, found)
    )
    emoji = found[0] if found else None
    if emoji is not None:
        result = result.rstrip("\r\n ")
    return result, emoji
