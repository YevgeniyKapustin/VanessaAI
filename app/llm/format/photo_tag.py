"""Photo-send marker parsing.

The compose model may append ``[photo:<index>]`` (its own final line, at most
one) when one of the photos listed in the album fits the message. This helper
strips the marker (code blocks left untouched) and returns the chosen index; the
pipeline resolves the index to the photo's ``telegram_file_id`` so the bot can
re-send it.
"""

import re

_FENCED_CODE = re.compile(r"```[\s\S]*?```", re.DOTALL)
_MARKER = re.compile(r"\[photo\s*:\s*(\d{1,3})\s*\]", re.IGNORECASE)


def extract_photo_index(reply: str) -> tuple[str, int | None]:
    """Strip ``[photo:N]`` markers; return ``(clean_reply, index_or_None)``."""
    if not reply:
        return reply, None

    found: int | None = None

    def repl(match: re.Match[str]) -> str:
        nonlocal found
        if found is None:
            found = int(match.group(1))
        return ""

    parts: list[str] = []
    last = 0
    for match in _FENCED_CODE.finditer(reply):
        if match.start() > last:
            parts.append(_MARKER.sub(repl, reply[last : match.start()]))
        parts.append(match.group(0))
        last = match.end()

    if last < len(reply):
        parts.append(_MARKER.sub(repl, reply[last:]))

    result = "".join(parts) if parts else reply
    # The marker is meant to sit on its own final line; drop the leftover newline.
    if found is not None:
        result = result.rstrip("\r\n ")
    return result, found
