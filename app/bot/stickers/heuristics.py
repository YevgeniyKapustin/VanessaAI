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
_LAUGH = re.compile(r"(лол|хах|ахах|хихи|хех|ржу|😂|🤣)", re.IGNORECASE)
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

# Explicit user requests to send a sticker. When matched the sticker gate is
# bypassed entirely (no probability roll, no cooldown) — a direct request must
# always be honoured.
_STICKER_REQUEST = re.compile(
    r"\b(кинь|скинь|дай|сбрось|пришли|покажи|кидай|брось|дропни|шл(и|ёшь))\s+"
    r"(мне\s+)?(стикер|стик|наклейку)\b"
    r"|\b(стикер|стик)\s+(кинь|скинь|дай|сбрось|пришли|кидай|брось)\b"
    r"|send\s+(me\s+)?a\s+sticker\b",
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
    tags: list[str] = []
    if _GREETING.search(text):
        tags.append("greeting")
    if _FAREWELL.search(text):
        tags.append("farewell")
    if _LAUGH.search(text):
        tags.append("delight")
    if _SHRUG.search(text):
        # no dedicated shrug sticker → the thinking 🤔 sticker fits «хз/не знаю»
        tags.append("thinking")
    if _THINKING.search(text):
        tags.append("thinking")
    if _FACEPALM.search(text):
        # no dedicated facepalm sticker → the burning 😮‍💨 sticker fits «блин/капец»
        tags.append("irritation")
    if _APPROVAL.search(text):
        # no dedicated approval sticker → the heart ❤️ sticker fits «да/согласна»
        tags.append("love")
    return tags
