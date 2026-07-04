from __future__ import annotations

import re

from app.core.messages import ContextMessage

_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_STOP = frozenset(
    {
        "ты",
        "тебя",
        "тебе",
        "это",
        "вот",
        "ну",
        "же",
        "ли",
        "бы",
        "да",
        "нет",
        "и",
        "а",
        "но",
        "уже",
        "ещё",
        "еще",
        "как",
        "что",
        "not",
        "the",
    }
)


def _normalize(text: str) -> str:
    lowered = text.lower().replace("ё", "е")
    cleaned = _PUNCT_RE.sub(" ", lowered)
    return _SPACE_RE.sub(" ", cleaned).strip()


def _word_overlap_ratio(left: str, right: str) -> float:
    left_words = set(_normalize(left).split())
    right_words = set(_normalize(right).split())
    if not left_words or not right_words:
        return 0.0
    shared = left_words & right_words
    return len(shared) / min(len(left_words), len(right_words))


def messages_echo(user_text: str, bot_text: str, *, threshold: float = 0.72) -> bool:
    user_norm = _normalize(user_text)
    bot_norm = _normalize(bot_text)
    if len(user_norm) < 12 or len(bot_norm) < 12:
        return False
    if user_norm == bot_norm:
        return True
    if user_norm in bot_norm or bot_norm in user_norm:
        return True
    return _word_overlap_ratio(user_text, bot_text) >= threshold


def has_substantive_addition(user_text: str, bot_text: str) -> bool:
    user_words = set(_normalize(user_text).split())
    bot_words = set(_normalize(bot_text).split())
    new_words = [
        word
        for word in user_words - bot_words
        if len(word) >= 3 and word not in _STOP
    ]
    if "?" in user_text:
        return len(new_words) >= 1
    return len(new_words) >= 3


def _last_assistant_text(recent_messages: list[ContextMessage]) -> str | None:
    for message in reversed(recent_messages):
        if message.role == "assistant" and message.content.strip():
            return message.content.strip()
    return None


def quote_loop_depth(recent_messages: list[ContextMessage]) -> int:
    depth = 0
    index = len(recent_messages) - 1
    while index >= 0:
        if recent_messages[index].role != "user":
            index -= 1
            continue
        assistant_index = index - 1
        while assistant_index >= 0 and recent_messages[assistant_index].role != "assistant":
            assistant_index -= 1
        if assistant_index < 0:
            break
        user_text = recent_messages[index].content
        bot_text = recent_messages[assistant_index].content
        if not messages_echo(user_text, bot_text):
            break
        if has_substantive_addition(user_text, bot_text):
            break
        depth += 1
        index = assistant_index - 1
    return depth


def is_recursive_quote_loop(
    text: str,
    recent_messages: list[ContextMessage],
    *,
    reply_to_bot: bool = False,
) -> bool:
    bot_text = _last_assistant_text(recent_messages)
    if not bot_text:
        return False
    if not messages_echo(text, bot_text):
        return False
    if has_substantive_addition(text, bot_text):
        return False
    if quote_loop_depth(recent_messages) >= 1:
        return True
    return reply_to_bot
