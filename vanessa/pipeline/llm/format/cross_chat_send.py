"""Extract the compose model's private cross-chat send instruction."""

from __future__ import annotations

import re
from collections.abc import Sequence

from vanessa.contracts.outbound import MESSAGE_MAX_CHARS
from vanessa.pipeline.llm.format.attribution import strip_attribution

_SEND_TAG = re.compile(
    r'<send_to_chat\s+id=["\'](-?\d+)["\']\s*>(.*?)</send_to_chat>',
    re.IGNORECASE | re.DOTALL,
)


def extract_cross_chat_send(
    reply: str,
    *,
    known_chat_ids: set[int],
    sender_is_owner: bool,
    owner_names: Sequence[str] = (),
) -> tuple[str, int | None, str | None]:
    matches = list(_SEND_TAG.finditer(reply))
    if not matches:
        return reply, None, None
    cleaned = _SEND_TAG.sub("", reply).strip()
    if not sender_is_owner or len(matches) != 1:
        return cleaned, None, None
    match = matches[0]
    chat_id = int(match.group(1))
    text = strip_attribution(match.group(2), owner_names)
    if chat_id not in known_chat_ids or not text or len(text) > MESSAGE_MAX_CHARS:
        return cleaned, None, None
    return cleaned, chat_id, text
