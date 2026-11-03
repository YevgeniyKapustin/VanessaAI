"""Extract the compose model's private DM instruction for the owner."""

from __future__ import annotations

import re

from vanessa.contracts.outbound import MESSAGE_MAX_CHARS

_DM_TAG = re.compile(r"<dm_owner>(.*?)</dm_owner>", re.IGNORECASE | re.DOTALL)


def extract_owner_dm(reply: str, *, allowed: bool) -> tuple[str, str | None]:
    """``(visible reply, owner DM text)``; the tag is always stripped."""
    matches = list(_DM_TAG.finditer(reply))
    if not matches:
        return reply, None
    cleaned = _DM_TAG.sub("", reply).strip()
    if not allowed or len(matches) != 1:
        return cleaned, None
    text = matches[0].group(1).strip()
    if not text:
        return cleaned, None
    return cleaned, text[:MESSAGE_MAX_CHARS]
