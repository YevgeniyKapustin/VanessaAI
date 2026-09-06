"""Photo-send marker parsing.

The compose model may append ``[photo:<index>]`` (its own final line, at most
one) when one of the photos listed in the album fits the message. This helper
strips the marker (code blocks left untouched) and returns the chosen index; the
pipeline resolves the index to the photo's ``telegram_file_id`` so the bot can
re-send it.
"""

import re

from vanessa.pipeline.llm.format.code_fences import (
    map_outside_fences as _map_outside_fences,
)

_MARKER = re.compile(r"\[photo\s*:\s*(\d{1,3})\s*\]", re.IGNORECASE)


def _take_photo_index(match: re.Match[str], found: list[int]) -> str:
    if not found:
        found.append(int(match.group(1)))
    return ""


def extract_photo_index(reply: str) -> tuple[str, int | None]:
    """Strip ``[photo:N]`` markers; return ``(clean_reply, index_or_None)``."""
    if not reply:
        return reply, None

    found: list[int] = []
    result = _map_outside_fences(
        reply,
        lambda segment: _MARKER.sub(
            lambda match: _take_photo_index(match, found),
            segment,
        ),
    )
    index = found[0] if found else None
    # The marker is meant to sit on its own final line; drop the leftover newline.
    if index is not None:
        result = result.rstrip("\r\n ")
    return result, index
