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

_ADDRESS_SEPARATOR = r"(?:,|:|…|\.\.\.|—)"
_ADDRESS_WRAP = r"[«„“\"'»”']?"
_DIGITS_ONLY = re.compile(r"^\d+$")


def _sender_name_tokens(sender_name: str) -> list[str]:
    """Split a display name into the tokens a bot might address the person by.

    Handles names like ``"Евгений (Капуста)"`` -> ``["Евгений", "Капуста"]``.
    Numeric-only tokens (fallback telegram ids) are ignored.
    """
    tokens: list[str] = []
    for token in re.split(r"[\s(),«»\"'„“\-]+", sender_name):
        token = token.strip(".,;:!?")
        if len(token) >= 3 and not _DIGITS_ONLY.match(token):
            tokens.append(token)
    return tokens


def _leading_address_pattern(name: str) -> re.Pattern[str]:
    """Regex matching an opening name-address like ``«Евгений, ...`` / ``Евгений: ...``."""
    core = re.escape(name)
    return re.compile(
        rf"^\s*{_ADDRESS_WRAP}{core}{_ADDRESS_WRAP}\s*{_ADDRESS_SEPARATOR}\s*",
        re.IGNORECASE,
    )


def strip_leading_address(text: str, sender_name: str | None = None) -> str:
    """Remove a leading name-address from a reply (e.g. «Евгений, …»).

    The persona must not call the addressee by name — who she's talking to is
    obvious from the reply/quote context. Enforced here deterministically (in
    addition to the prompt) so a reply never opens with the sender's name.
    Only a genuine address prefix (name followed by a comma/colon/ellipsis) is
    stripped; a name used as a sentence subject ("Евгений знает...") is kept.
    """
    if not sender_name or not text:
        return text
    stripped = text.strip()
    if not stripped:
        return stripped
    for token in _sender_name_tokens(sender_name):
        match = _leading_address_pattern(token).match(stripped)
        if match is None:
            continue
        # Never return an empty reply: if the whole text was just the name,
        # keep it as-is rather than sending an empty message.
        result = stripped[match.end() :].strip()
        return result or stripped
    return stripped


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
