"""Reply text → what a voice can actually say.

Replies are written for a chat window: markdown markers, links and emoji sound
like noise when read aloud ("звёздочка звёздочка"). The same cleanup serves the
Telegram voice note and any future speech adapter.
"""

from __future__ import annotations

import re

#: A voice note is a short answer; a wall of text is not worth the credits.
_MAX_CHARS = 2_000
_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"(?:https?://|www\.)\S+")
_EMOJI = re.compile("[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff\ufe0f\u200d]")
_MARKDOWN = re.compile(r"[*_~#>|]+")
_SPACES = re.compile(r"[ \t]+")
_LINE_EDGES = re.compile(r"[ \t]*\n[ \t]*")
_BLANK_LINES = re.compile(r"\n{2,}")
_TRAILING = " ,;:—–-"


def speakable_text(text: str | None) -> str:
    """Strip everything that would be spelled out instead of spoken."""
    if not text:
        return ""
    cleaned = _FENCE.sub(" ", text)
    cleaned = _INLINE_CODE.sub(r"\1", cleaned)
    cleaned = _LINK.sub(r"\1", cleaned)
    cleaned = _URL.sub("", cleaned)
    cleaned = _EMOJI.sub("", cleaned)
    cleaned = _MARKDOWN.sub("", cleaned)
    cleaned = _SPACES.sub(" ", cleaned)
    cleaned = _LINE_EDGES.sub("\n", cleaned)
    cleaned = _BLANK_LINES.sub("\n", cleaned)
    return _truncate(cleaned.strip())


def _truncate(text: str) -> str:
    if len(text) <= _MAX_CHARS:
        return text
    cut = text[:_MAX_CHARS]
    space = cut.rfind(" ")
    return (cut[:space] if space > 0 else cut).rstrip(_TRAILING) + "…"
