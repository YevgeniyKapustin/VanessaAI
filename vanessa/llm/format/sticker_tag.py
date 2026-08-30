import logging
import re

from vanessa.config.content import get_content
from vanessa.observability.metrics import sticker_tagged_total, sticker_unknown_tags_total

logger = logging.getLogger(__name__)


def _catalog_sticker_tags() -> frozenset[str]:
    """Tags that actually have a sticker in the pack (the single source of truth).

    Derived from config/content/stickers.yaml so the allowed set can never drift
    from the stickers that really exist. Anything else the model emits is stripped
    and dropped (or soft-mapped through ``TAG_ALIASES``).
    """
    return frozenset(get_content().stickers.available_tags)


# Tags the LLM is allowed to suggest — the personality tags that have a sticker in
# the pack. These are the only tags the pipeline will pass on to the bot (anything
# else is stripped and dropped or soft-mapped).
KNOWN_STICKER_TAGS = _catalog_sticker_tags()


def _catalog_tag_aliases() -> dict[str, str]:
    """Normalized alias map: invented LLM tag -> closest real tag.

    Loaded from config/content/stickers.yaml ``tag_aliases``. Alias targets that
    don't resolve to a real pack tag are ignored so the fallback can never point
    at a sticker that doesn't exist.
    """
    aliases: dict[str, str] = {}
    for alias, target in get_content().stickers.tag_aliases.items():
        alias_key = alias.strip().lower()
        target_key = target.strip().lower()
        if alias_key and target_key and target_key in KNOWN_STICKER_TAGS:
            aliases[alias_key] = target_key
    return aliases


# Soft fallback for tags the model invents but the pack doesn't have.
TAG_ALIASES = _catalog_tag_aliases()

_FENCED_CODE = re.compile(r"```[\s\S]*?```", re.DOTALL)
_MARKER = re.compile(
    r"\[sticker\s*:\s*([a-zA-Z0-9_-]+)\s*\]",
    re.IGNORECASE,
)


def _strip_markers(segment: str) -> tuple[str, str | None]:
    """Remove [sticker:...] markers from a non-code segment.

    Returns the cleaned segment and the first known tag found (``None``
    otherwise). Unknown tags are soft-mapped through ``TAG_ALIASES`` when an
    alias exists, otherwise they are dropped. Unknown tags never leak into the
    reply text and are logged + counted so model drift stays visible.
    """
    found: str | None = None

    def repl(match: re.Match[str]) -> str:
        nonlocal found
        candidate = match.group(1).lower()
        if candidate in KNOWN_STICKER_TAGS:
            sticker_tagged_total.labels(tag=candidate).inc()
            if found is None:
                found = candidate
            return ""
        mapped = TAG_ALIASES.get(candidate)
        if mapped is not None:
            sticker_unknown_tags_total.labels(action="mapped").inc()
            sticker_tagged_total.labels(tag=mapped).inc()
            logger.info(
                "sticker_unknown_tag raw=%s action=mapped target=%s",
                candidate,
                mapped,
            )
            if found is None:
                found = mapped
        else:
            sticker_unknown_tags_total.labels(action="dropped").inc()
            logger.info(
                "sticker_unknown_tag raw=%s action=dropped target=-",
                candidate,
            )
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
