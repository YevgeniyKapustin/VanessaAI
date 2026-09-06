# Token helpers for humor quote scoring. Cyrillic matches Russian chat text.
import re

_TOKEN = re.compile(r"[a-zа-яё]{4,}", re.IGNORECASE)
_STOP = frozenset(
    {
        "этот",
        "этого",
        "тебе",
        "тебя",
        "меня",
        "вообще",
        "просто",
        "очень",
        "когда",
        "потому",
        "сначала",
    }
)
_THEME_OVERLAP_MIN = 2
_LONG_TOKEN_CHARS = 6


def _normalize(text: str) -> str:
    return text.replace("ё", "е").lower().strip()


def _distinctive_tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN.findall(_normalize(text))
        if token not in _STOP
    }


def _has_long_token_in(tokens: set[str], other: str) -> bool:
    normalized = _normalize(other)
    for token in tokens:
        if len(token) >= _LONG_TOKEN_CHARS and token in normalized:
            return True
    return False


def _weak_theme_repeat(tokens: set[str], overlap: set[str], other: str) -> bool:
    if len(tokens) == 1 and overlap:
        return True
    return _has_long_token_in(tokens, other)


def _theme_repeats_other(text: str, tokens: set[str], other: str) -> bool:
    if other == text:
        return False
    overlap = tokens & _distinctive_tokens(other)
    if len(overlap) >= _THEME_OVERLAP_MIN:
        return True
    return _weak_theme_repeat(tokens, overlap, other)


def _theme_repeat_count(text: str, corpus: list[str]) -> int:
    tokens = _distinctive_tokens(text)
    if not tokens:
        return 0
    return sum(1 for other in corpus if _theme_repeats_other(text, tokens, other))
