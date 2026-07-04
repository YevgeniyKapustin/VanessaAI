import re

_BOT_NAME_RE_CACHE: dict[tuple[str, ...], re.Pattern[str]] = {}


def compile_bot_name_pattern(names: tuple[str, ...] | list[str]) -> re.Pattern[str] | None:
    key = tuple(names)
    if key in _BOT_NAME_RE_CACHE:
        return _BOT_NAME_RE_CACHE[key]
    patterns: list[str] = []
    for name in key:
        normalized = name.strip().lower().replace("ё", "е")
        if not normalized:
            continue
        if len(normalized) >= 5:
            stem = normalized[: max(4, len(normalized) - 1)]
            patterns.append(rf"\b{re.escape(stem)}\w*")
        else:
            patterns.append(rf"\b{re.escape(normalized)}\w*")
    if not patterns:
        return None
    compiled = re.compile("|".join(patterns), re.IGNORECASE)
    _BOT_NAME_RE_CACHE[key] = compiled
    return compiled


def text_mentions_bot_name(text: str, names: tuple[str, ...]) -> bool:
    pattern = compile_bot_name_pattern(names)
    if pattern is None:
        return False
    normalized = text.lower().replace("ё", "е")
    return bool(pattern.search(normalized))
