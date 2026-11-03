"""Deterministic check that a message asks for an answer.

The gate must decide before the planner whether an agent's message deserves
the proxy path. Questions and direct requests to the owner count; plain
bot-to-bot chatter does not.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[а-яёa-z]+")

_QUESTION_WORDS = frozenset(
    {
        "когда",
        "почему",
        "зачем",
        "где",
        "куда",
        "кто",
        "какой",
        "какая",
        "какое",
        "какие",
        "сколько",
        "можно",
        "можешь",
        "сможешь",
        "планируешь",
        "успеешь",
        "будешь",
        "нужен",
        "нужна",
        "нужны",
        "готов",
        "готова",
        "знаешь",
        "помнишь",
    }
)

_REQUEST_WORDS = frozenset(
    {
        "скинь",
        "дай",
        "покажи",
        "подскажи",
        "проверь",
        "глянь",
        "сделай",
        "запусти",
        "обнови",
        "напомни",
        "пришли",
    }
)

_MIN_WORDS = 2


def looks_like_question(text: str) -> bool:
    """A question mark or a question/request word in a message of 3+ words."""
    stripped = text.strip()
    if "?" in stripped or "？" in stripped:
        return True
    words = _WORD_RE.findall(stripped.casefold())
    if len(words) < _MIN_WORDS:
        return False
    return any(
        word in _QUESTION_WORDS or word in _REQUEST_WORDS for word in words
    )
