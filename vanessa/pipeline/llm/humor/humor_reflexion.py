import re

_THEME = re.compile(r"[a-zа-яё]{4,}", re.IGNORECASE)
_STOP = frozenset({"мем", "шутка", "подкол"})
_SHORT_QUOTE_CHARS = 15
_LONG_QUOTE_CHARS = 120


def _theme_overlap_score(theme_tokens: set[str], quote_tokens: set[str]) -> float:
    if not theme_tokens:
        return 0.0
    overlap = len(theme_tokens & quote_tokens)
    if overlap == 0:
        return -2.0
    return overlap * 2.0


def _quote_length_penalty(quote: str) -> float:
    score = 0.0
    if len(quote) < _SHORT_QUOTE_CHARS:
        score -= 1.0
    if len(quote) > _LONG_QUOTE_CHARS:
        score -= 0.5
    return score


def _quote_theme_score(quote: str, theme_tokens: set[str]) -> float:
    quote_tokens = {token.lower() for token in _THEME.findall(quote)}
    return _theme_overlap_score(theme_tokens, quote_tokens) + _quote_length_penalty(
        quote
    )


def _reject_scored_quote(score: float, quote: str, kept: list[str]) -> bool:
    if score < 0:
        return True
    return quote in kept


def _select_scored_quotes(
    scored: list[tuple[float, str]],
    max_quotes: int,
) -> list[str]:
    kept: list[str] = []
    for score, quote in scored:
        if _reject_scored_quote(score, quote, kept):
            continue
        kept.append(quote)
        if len(kept) >= max_quotes:
            break
    return kept


def _keep_scored_quotes(
    scored: list[tuple[float, str]],
    quotes: list[str],
    max_quotes: int,
) -> list[str]:
    kept = _select_scored_quotes(scored, max_quotes)
    if not kept:
        return quotes[:max_quotes]
    return kept


def reflexion_filter_humor_quotes(
    quotes: list[str],
    *,
    humor_query: str,
    user_message: str,
    max_quotes: int,
) -> list[str]:
    if not quotes:
        return []

    theme_tokens = {
        token.lower()
        for token in _THEME.findall(f"{humor_query} {user_message}")
        if token.lower() not in _STOP
    }

    scored: list[tuple[float, str]] = [
        (_quote_theme_score(quote, theme_tokens), quote) for quote in quotes
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    return _keep_scored_quotes(scored, quotes, max_quotes)
