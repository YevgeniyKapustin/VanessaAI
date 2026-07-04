import re

_LOWERCASE_OK = frozenset({"хз", "ок", "ага", "угу", "мм", "..."})
_SENTENCE_START = re.compile(
    r"(^|[.!?…]\s+|\.{3}\s+)([a-zа-яё])",
)


def capitalize_sentences(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped
    if stripped.lower() in _LOWERCASE_OK:
        return stripped

    def repl(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2).upper()

    return _SENTENCE_START.sub(repl, stripped)
