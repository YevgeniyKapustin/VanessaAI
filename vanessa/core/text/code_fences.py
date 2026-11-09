from __future__ import annotations

import re
from collections.abc import Callable

FENCED_CODE = re.compile(r"```[\s\S]*?```", re.DOTALL)


def map_outside_fences(text: str, mapper: Callable[[str], str]) -> str:
    """Apply ``mapper`` to every non-code segment, keeping code fences intact."""
    parts: list[str] = []
    cursor = 0
    for match in FENCED_CODE.finditer(text):
        if match.start() > cursor:
            parts.append(mapper(text[cursor : match.start()]))
        parts.append(match.group(0))
        cursor = match.end()
    if cursor < len(text):
        parts.append(mapper(text[cursor:]))
    return "".join(parts)
