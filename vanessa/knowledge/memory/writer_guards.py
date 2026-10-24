"""Reject planner items that would become junk cards (bare links, no body)."""

from __future__ import annotations

import re

_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_WORD = re.compile(r"[^\W\d_]{2,}")


def has_url(text: str) -> bool:
    return bool(_URL.search(text))


def is_bare_url(text: str) -> bool:
    """True when the text has a link and no words outside it."""
    if not has_url(text):
        return False
    return not _WORD.search(_URL.sub(" ", text))


def card_label(text: str) -> str:
    """Card title/term, or "" when it is blank or only a link."""
    label = text.strip()
    if not label or is_bare_url(label):
        return ""
    return label


def has_body(body: str) -> bool:
    return bool(body.strip())
