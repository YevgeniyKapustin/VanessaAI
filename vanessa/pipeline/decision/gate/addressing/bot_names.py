import re

_BOT_NAME_RE_CACHE: dict[tuple[str, ...], re.Pattern[str]] = {}
_YO_TO_YE = ("ё", "е")
_MIN_NAME_LEN_FOR_STEM = 5
_STEM_KEEP = 4


def _name_regex(name: str) -> str | None:
    normalized = name.strip().lower().replace(*_YO_TO_YE)
    if not normalized:
        return None
    if len(normalized) >= _MIN_NAME_LEN_FOR_STEM:
        stem = normalized[: max(_STEM_KEEP, len(normalized) - 1)]
        return rf"\b{re.escape(stem)}\w*"
    return rf"\b{re.escape(normalized)}\w*"


def _name_patterns(names: tuple[str, ...]) -> list[str]:
    patterns: list[str] = []
    for name in names:
        pattern = _name_regex(name)
        if pattern is None:
            continue
        patterns.append(pattern)
    return patterns


def compile_bot_name_pattern(names: tuple[str, ...] | list[str]) -> re.Pattern[str] | None:
    key = tuple(names)
    if key in _BOT_NAME_RE_CACHE:
        return _BOT_NAME_RE_CACHE[key]
    patterns = _name_patterns(key)
    if not patterns:
        return None
    compiled = re.compile("|".join(patterns), re.IGNORECASE)
    _BOT_NAME_RE_CACHE[key] = compiled
    return compiled


def text_mentions_bot_name(text: str, names: tuple[str, ...]) -> bool:
    pattern = compile_bot_name_pattern(names)
    if pattern is None:
        return False
    normalized = text.lower().replace(*_YO_TO_YE)
    return bool(pattern.search(normalized))
