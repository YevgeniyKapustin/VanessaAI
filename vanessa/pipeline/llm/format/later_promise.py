"""Detect a reply that promises to look something up and send it later.

Such a promise is true only when a work lookup runs this turn. Without one,
nothing will ever be sent, so the compose stage regenerates the reply.
"""

import re

_LOOK = r"(?:гляну|погляжу|посмотрю|проверю|чекну|найду|поищу|выясню|разузнаю)"
_SEND = r"(?:скину|пришлю|отпишусь|сообщу|доложу)"
_NOW = r"(?:ща|щас|сейчас|погоди|подожди|секунду|сек|минуту)"

_LOOK_RE = re.compile(rf"\b{_LOOK}\b", re.IGNORECASE)
_SEND_RE = re.compile(rf"\b{_SEND}\b", re.IGNORECASE)
_NOW_LOOK_RE = re.compile(rf"\b{_NOW}\b[\s,—–-]*{_LOOK}\b", re.IGNORECASE)
_SEND_LATER_RE = re.compile(
    rf"\b{_SEND}\b[\s,]+(?:\w+[\s,]+)?(?:списком|позже|потом|попозже)\b",
    re.IGNORECASE,
)


def promises_later_result(text: str) -> bool:
    """True when the reply says she will look and send the result later."""
    if not text:
        return False
    if _NOW_LOOK_RE.search(text) or _SEND_LATER_RE.search(text):
        return True
    return bool(_LOOK_RE.search(text) and _SEND_RE.search(text))
