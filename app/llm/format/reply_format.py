import re

_LOWERCASE_OK = frozenset({"хз", "ок", "ага", "угу", "мм", "..."})
_SENTENCE_START = re.compile(
    r"(^|[.!?…]\s+|\.{3}\s+)([a-zа-яё])",
)
_FENCED_CODE = re.compile(r"```[\s\S]*?```", re.DOTALL)


def capitalize_sentences(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped
    if stripped.lower() in _LOWERCASE_OK:
        return stripped

    parts: list[str] = []
    last = 0
    for match in _FENCED_CODE.finditer(stripped):
        if match.start() > last:
            parts.append(_capitalize_prose(stripped[last : match.start()]))
        parts.append(match.group(0))
        last = match.end()
    if last < len(stripped):
        parts.append(_capitalize_prose(stripped[last:]))
    return "".join(parts) if parts else _capitalize_prose(stripped)


def _capitalize_prose(text: str) -> str:
    if not text:
        return text

    def repl(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2).upper()

    return _SENTENCE_START.sub(repl, text)
