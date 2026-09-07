from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PresenceTurn:
    message: str
    display_name: str
    scene_jpeg: bytes | None = None


@dataclass(frozen=True, slots=True)
class PresenceReply:
    action: str
    reason: str
    text: str | None = None
