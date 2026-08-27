import re

_LOWERCASE_OK = frozenset({"хз", "ок", "ага", "угу", "мм", "..."})
_SENTENCE_START = re.compile(
    r"(^|[.!?…]\s+|\.{3}\s+)([a-zа-яё])",
)
_FENCED_CODE = re.compile(r"```[\s\S]*?```", re.DOTALL)
_LICH_SPELLING = re.compile(r"(?<![а-яё])([Лл])ич(?![ьЬа-яё])")


def fix_participant_spelling(text: str) -> str:
    return _LICH_SPELLING.sub(r"\1ичь", text)


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
    result = "".join(parts) if parts else _capitalize_prose(stripped)
    return fix_participant_spelling(result)


def _capitalize_prose(text: str) -> str:
    if not text:
        return text

    def repl(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2).upper()

    return _SENTENCE_START.sub(repl, text)


_TRAILING_PERIODS = re.compile(r"\.+$")


def strip_trailing_periods(text: str) -> str:
    """Remove the trailing period(s) of a reply.

    The persona avoids a period at the very end of a message. The rule is
    enforced here instead of in the prompt so the model doesn't spend its
    attention budget on punctuation. An intentional ellipsis ('...') is kept.
    """
    stripped = text.rstrip()
    if not stripped or stripped.endswith("..."):
        return stripped
    return _TRAILING_PERIODS.sub("", stripped)
