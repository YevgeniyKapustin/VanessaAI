"""Portrait frontmatter defaults. ``or`` coalescing lives here so callers stay flat."""

from __future__ import annotations

import hashlib
import json


def field_text(*values: object) -> str:
    """``str(a or b or "")`` without stacking ``or`` in the caller."""
    for value in values:
        if value:
            return str(value)
    return ""


def note_meta(note) -> dict:
    return dict(note.meta or {})


def has_chat_identity(meta: dict) -> bool:
    """Portraits are for chat participants: cards with a ``telegram_id``."""
    return bool(str(meta.get("telegram_id") or "").strip())


def portrait_is_current(meta: dict, signature: str, *, force: bool) -> bool:
    if force:
        return False
    return str(meta.get("portrait_signature") or "") == signature


def needs_portrait(meta: dict, signature: str, *, force: bool) -> bool:
    """A chat participant's card whose portrait is missing or stale."""
    if not has_chat_identity(meta):
        return False
    return not portrait_is_current(meta, signature, force=force)


def clip_dossier(body: object, max_chars: int) -> str:
    dossier = (body or "").strip()
    if not dossier:
        return ""
    if len(dossier) <= max_chars:
        return dossier
    return dossier[:max_chars].rstrip() + "\n…"


def alias_names(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(alias).strip() for alias in raw if str(alias).strip()]


def portrait_prompt_fields(
    meta: dict,
    relative_path: str,
) -> tuple[str, list[str], str, object]:
    nickname = field_text(meta.get("nickname"), meta.get("id"), relative_path)
    mood = field_text(meta.get("mood")).strip()
    previous = meta.get("portrait") or ""
    return nickname, alias_names(meta.get("aliases")), mood, previous


def dossier_signature(note) -> str:
    """Stable fingerprint of the dossier (body + identity fields)."""
    meta = note.meta or {}
    payload = {
        "body": note.body or "",
        "nickname": field_text(meta.get("nickname")),
        "mood": field_text(meta.get("mood")),
        "aliases": meta.get("aliases") or [],
        "telegram_id": meta.get("telegram_id"),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha1(  # noqa: S324 - dossier fingerprint, not a password/MAC
        canonical.encode("utf-8")
    ).hexdigest()
