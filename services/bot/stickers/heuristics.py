import re

# High-confidence text signals used as a fallback when the LLM didn't tag a reply.
_GREETING = re.compile(
    r"^\s*(ну\s+)?(привет|здарова|здорово|салют|хай|hello|hi|"
    r"добрый\s+(день|вечер|утро)|снова\s+ты)\b",
    re.IGNORECASE,
)
_FAREWELL = re.compile(
    r"\b(пока|до\s+связи|до\s+завтра|бывай|бывайте|удачи|покедова|бай)\b",
    re.IGNORECASE,
)
_LAUGH = re.compile(
    r"(лол|хах|ахах|хихи|хех|ржу|😂|🤣)",
    re.IGNORECASE,
)
_SHRUG = re.compile(
    r"\b(хз|не\s+знаю|понятия\s+не\s+имею|без\s+понятия)\b",
    re.IGNORECASE,
)
_THINKING = re.compile(
    r"\b(думаю|дай\s+подумать|подумаю|соображаю|хм|ммм)\b",
    re.IGNORECASE,
)
_FACEPALM = re.compile(
    r"\b(гениально|оригинально|капец|блин|вот\s+это\s+да|ох\s+уж)\b",
    re.IGNORECASE,
)
_APPROVAL = re.compile(
    r"^\s*(да\b|именно\b|точно\b|верно\b|согласна?\b|естественно\b)",
    re.IGNORECASE,
)
_TAG_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (_GREETING, "greeting"),
    (_FAREWELL, "farewell"),
    (_LAUGH, "delight"),
    (_SHRUG, "thinking"),
    (_THINKING, "thinking"),
    (_FACEPALM, "irritation"),
    (_APPROVAL, "love"),
)

# Explicit user requests to send a sticker. When matched the sticker gate is
# bypassed entirely (no probability roll, no cooldown) — a direct request must
# always be honoured.
#
# Allowed verbs include «отправь/отправить/отправляй» (the most natural Russian
# way to say "send a sticker") alongside the imperative forms. Between the verb
# and the sticker word an optional «мне» and/or a polite particle («пожалуйста»,
# «плиз») are allowed: «отправь стикер», «отправь мне наклейку»,
# «кинь плиз стикер», «скинь пожалуйста стикер», «стикер отправь».
_STICKER_VERBS = (
    r"кинь|скинь|дай|сбрось|пришли|покажи|кидай|брось|дропни"
    r"|отправь|отправить|отправляй|шли|шлёшь|шлите"
)
_STICKER_REQUEST = re.compile(
    rf"\b(?:{_STICKER_VERBS})\s+(?:мне\s+)?(?:пожалуйста\s+|плиз\s+)?"
    r"(?:стикер|стик|наклейку)\b"
    rf"|\b(?:стикер|стик|наклейку)\s+(?:мне\s+)?(?:пожалуйста\s+|плиз\s+)?"
    rf"(?:{_STICKER_VERBS})\b"
    r"|send\s+(?:me\s+)?a\s+sticker\b",
    re.IGNORECASE,
)


def is_sticker_request(text: str | None) -> bool:
    """True when the user explicitly asked the bot to send a sticker."""
    if not text:
        return False
    return bool(_STICKER_REQUEST.search(text))


def reply_tags(reply: str | None) -> list[str]:
    """Ordered candidate tags derived from the reply text (best first).

    Order matters: the decider takes the first tag that has stickers in the catalog.
    """
    if not reply:
        return []
    text = reply.strip()
    return [tag for pattern, tag in _TAG_RULES if pattern.search(text)]
