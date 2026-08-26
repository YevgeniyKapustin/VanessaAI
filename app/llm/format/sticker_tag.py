import re

from app.config.content import get_content


def _catalog_sticker_tags() -> frozenset[str]:
    """Tags that actually have a sticker in the pack (the single source of truth).

    Derived from config/content/stickers.yaml so the allowed set can never drift
    from the stickers that really exist. Anything else the model emits is stripped
    and dropped.
    """
    return frozenset(get_content().stickers.available_tags)


# Tags the LLM is allowed to suggest — the personality tags that have a sticker in
# the pack. These are the only tags the pipeline will pass on to the bot (anything
# else is stripped and dropped).
KNOWN_STICKER_TAGS = _catalog_sticker_tags()

_FENCED_CODE = re.compile(r"```[\s\S]*?```", re.DOTALL)
_MARKER = re.compile(
    r"\[sticker\s*:\s*([a-zA-Z0-9_-]+)\s*\]",
    re.IGNORECASE,
)


def _strip_markers(segment: str) -> tuple[str, str | None]:
    """Remove [sticker:...] markers from a non-code segment.

    Returns the cleaned segment and the first known tag found (``None`` otherwise).
    Unknown tags are still stripped so they never leak into the reply text.
    """
    found: str | None = None

    def repl(match: re.Match[str]) -> str:
        nonlocal found
        candidate = match.group(1).lower()
        if found is None and candidate in KNOWN_STICKER_TAGS:
            found = candidate
        return ""

    cleaned = _MARKER.sub(repl, segment)
    return cleaned, found


def extract_sticker_tag(reply: str) -> tuple[str, str | None]:
    """Strip the LLM's sticker marker out of a reply.

    The model may append ``[sticker:<tag>]`` (its own line, at most one) when a
    sticker genuinely fits. This helper removes every occurrence — code blocks are
    left untouched — and returns ``(clean_reply, tag_or_None)``.

    The cleaned text is what gets stored and sent; the tag is what the bot uses to
    pick a sticker (after its own anti-spam gates).
    """
    if not reply:
        return reply, None

    parts: list[str] = []
    tag: str | None = None
    last = 0
    for match in _FENCED_CODE.finditer(reply):
        if match.start() > last:
            cleaned, found = _strip_markers(reply[last : match.start()])
            parts.append(cleaned)
            if tag is None and found is not None:
                tag = found
        parts.append(match.group(0))
        last = match.end()

    if last < len(reply):
        cleaned, found = _strip_markers(reply[last:])
        parts.append(cleaned)
        if tag is None and found is not None:
            tag = found

    result = "".join(parts) if parts else reply
    # The marker is meant to sit on its own final line; drop the leftover newline.
    if tag is not None:
        result = result.rstrip("\r\n ")
    return result, tag
