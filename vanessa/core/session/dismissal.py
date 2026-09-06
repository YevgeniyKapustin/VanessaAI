import re

_DISMISSAL_PATTERNS = (
    r"\b(перестань|прекрати|заткнись|замолчи|отстань|молчи)\b",
    r"\b(не\s+)?(отвечай|пиши)\b",
    r"\bхватит\b(?!\s+ли\b)(\s*(тебе|мне))?\s*(отвечать|писать)?",
    r"^хватит[.!?]?\s*$",
    r"\bзакрой\s+(контекст|диалог|сессию)\b",
    (
        r"\b(уйди|уходи|убирайся|сгинь|сгиньте|исчезни|исчезай|"
        r"свали|отвали|отстань)\b"
    ),
    r"\b(оставь|не\s+трогай)\s+(меня|нас)(\s+в\s+покое)?\b",
    r"\bдостаточно\b(\s*(тебе|мне))?\s*(отвечать|писать)?",
    r"\bможешь\s+молчать\b",
    r"\bотключись\b",
    r"\b(ванесса|vanessa)[,.\s]+(хватит|молчи|замолчи|отстань)\b",
    r"\b(хватит|молчи|замолчи|отстань)[,.\s]+(ванесса|vanessa)\b",
)
DISMISSAL_RE = re.compile("|".join(_DISMISSAL_PATTERNS), re.IGNORECASE)


def is_dismissal_request(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return bool(DISMISSAL_RE.search(normalized))
