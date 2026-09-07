from __future__ import annotations

from services.presence.avatar import AvatarConfig, Gesture


def pick_gesture(text: str, avatar: AvatarConfig) -> Gesture | None:
    lowered = text.casefold()
    for needle, name in avatar.emotion_map.items():
        if needle.casefold() in lowered:
            return avatar.gestures.get(name)
    return None
