"""When a Telegram reply goes out as a voice note.

Voice is opt-in per turn: she speaks when the message asks her to
(«скажи голосом», «озвучь»), and answers a voice note with a voice note.
Every other reply stays text — and a TTS failure falls back to that text too,
so a missing ElevenLabs key changes nothing but the delivery.
"""

from __future__ import annotations

import re

#: Modes that speak every reply, whatever the user asked for.
ALWAYS_VOICE_MODES = frozenset({"voice_and_text", "voice_only"})
#: Default mode: speak only on an explicit request or in answer to a voice note.
ON_REQUEST_MODE = "on_request"

_VOICE_REQUEST = re.compile(
    r"(?:"
    r"голосов\w*"
    r"|голосом"
    r"|вслух"
    r"|озвуч\w*"
    r"|произнес\w*"
    r"|voice\s+(?:note|message)"
    r"|out\s+loud"
    r")",
    re.IGNORECASE,
)


def wants_voice_reply(text: str | None) -> bool:
    """True when the message explicitly asks her to answer with her voice."""
    return bool(text) and _VOICE_REQUEST.search(text) is not None


def should_send_voice(
    *,
    mode: str,
    requested: bool,
    replied_to_voice: bool,
) -> bool:
    normalized = (mode or "").strip().lower()
    if normalized in ALWAYS_VOICE_MODES:
        return True
    if normalized != ON_REQUEST_MODE:
        return False
    return requested or replied_to_voice


def omits_text(*, voice_sent: bool, mode: str) -> bool:
    """``voice_and_text`` keeps the text; every other mode lets voice stand alone."""
    return voice_sent and (mode or "").strip().lower() != "voice_and_text"
