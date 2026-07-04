import re

_THEME = re.compile(r"[a-zа-яё]{4,}", re.IGNORECASE)
_STOP = frozenset({"мем", "шутка", "подкол"})


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

    scored: list[tuple[float, str]] = []
    for quote in quotes:
        score = 0.0
        quote_tokens = {t.lower() for t in _THEME.findall(quote)}
        if theme_tokens:
            overlap = len(theme_tokens & quote_tokens)
            score += overlap * 2.0
            if overlap == 0:
                score -= 2.0
        if len(quote) < 15:
            score -= 1.0
        if len(quote) > 120:
            score -= 0.5
        scored.append((score, quote))

    scored.sort(key=lambda item: item[0], reverse=True)
    kept: list[str] = []
    for score, quote in scored:
        if score < 0:
            continue
        if quote in kept:
            continue
        kept.append(quote)
        if len(kept) >= max_quotes:
            break
    if not kept:
        return quotes[:max_quotes]
    return kept
