from __future__ import annotations

import re

from vanessa.core.messages import ContextMessage

_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_STOP = frozenset(
    {
        "ты",
        "тебя",
        "тебе",
        "тобой",
        "твой",
        "твоя",
        "твоё",
        "твое",
        "это",
        "этого",
        "эту",
        "этот",
        "эта",
        "вот",
        "там",
        "тут",
        "здесь",
        "ну",
        "же",
        "ли",
        "бы",
        "и",
        "а",
        "но",
        "или",
        "да",
        "нет",
        "уже",
        "ещё",
        "еще",
        "если",
        "что",
        "как",
        "где",
        "когда",
        "почему",
        "зачем",
        "кто",
        "который",
        "которая",
        "которые",
        "не",
        "ни",
        "то",
        "в",
        "на",
        "по",
        "с",
        "со",
        "к",
        "из",
        "у",
        "для",
        "про",
        "об",
        "обо",
        "о",
        "от",
        "до",
        "при",
    }
)

_MIN_REPEAT_TOKENS = 3
_PURE_REPEAT_COVERAGE = 0.6
_MIN_WINDOW_MESSAGES = 2


def message_tokens(text: str) -> set[str]:
    """Content words of a message: lowercased, punctuation stripped, stop words removed."""
    lowered = text.lower().replace("ё", "е")
    cleaned = _PUNCT_RE.sub(" ", lowered)
    words = [word for word in _SPACE_RE.sub(" ", cleaned).split() if len(word) > 1]
    return {word for word in words if word not in _STOP}


def _answered_later(messages: list[ContextMessage], start_index: int) -> bool:
    """Whether the user message at ``start_index`` received an assistant reply."""
    for message in messages[start_index + 1 :]:
        if message.role == "assistant":
            return True
        if message.role == "user":
            return False
    return False


def is_pure_repeat(current: set[str], prior: set[str]) -> bool:
    """A near-pure repeat: current adds no new content and keeps most of the prior.

    ``current`` must be a subset of ``prior`` (no new words) and cover at least 60%
    of it, so shortened re-asks count but genuine expansions do not.
    """
    if len(current) < _MIN_REPEAT_TOKENS or not prior:
        return False
    if not current <= prior:
        return False
    return len(current) / len(prior) >= _PURE_REPEAT_COVERAGE


def normalize_content(text: str) -> str:
    """Canonical form for exact repeated-message matching.

    Lowercases, normalizes ё→е, strips punctuation and collapses whitespace.
    Keeps stopwords (unlike ``message_tokens``) so short spam like «ванесса»
    matches «ванесса» exactly.
    """
    lowered = text.lower().replace("ё", "е")
    cleaned = _PUNCT_RE.sub(" ", lowered)
    return " ".join(_SPACE_RE.sub(" ", cleaned).split())


def _is_same_sender_user(message: ContextMessage, sender_telegram_id: int) -> bool:
    if message.role != "user":
        return False
    if not sender_telegram_id:
        return True
    return message.sender_telegram_id in (0, sender_telegram_id)


def _is_repeat_copy(
    message: ContextMessage,
    current: str,
    *,
    sender_telegram_id: int,
) -> bool:
    if not _is_same_sender_user(message, sender_telegram_id):
        return False
    return normalize_content(message.content or "") == current


def _has_repeat_count(
    current: str,
    recent: list[ContextMessage],
    *,
    sender_telegram_id: int,
    min_occurrences: int,
) -> bool:
    count = 0
    for message in recent:
        if not _is_repeat_copy(
            message,
            current,
            sender_telegram_id=sender_telegram_id,
        ):
            continue
        count += 1
        if count >= min_occurrences:
            return True
    return False


def is_repeated_message(
    text: str,
    recent: list[ContextMessage],
    *,
    sender_telegram_id: int = 0,
    min_occurrences: int = 2,
) -> bool:
    """Whether the same sender sent the same content at least ``min_occurrences``
    times within ``recent``.

    Independent of whether the earlier copies were answered — a burst of
    identical messages is spam, not a new question. When ``sender_telegram_id``
    is known, only same-sender copies count (a different person's similar
    message does not suppress this one).
    """
    min_occurrences = max(min_occurrences, 2)
    current = normalize_content(text)
    if not current:
        return False
    return _has_repeat_count(
        current,
        recent,
        sender_telegram_id=sender_telegram_id,
        min_occurrences=min_occurrences,
    )
