from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from app.config.settings import settings
from app.ingest.user_backfill import load_nicknames

_SPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _SPACE_RE.sub(" ", text.replace("ё", "е").lower()).strip()


def resolve_nicknames_path() -> Path:
    configured = Path(settings.nicknames_config_path)
    if configured.is_file():
        return configured
    project_root = Path(__file__).resolve().parents[2]
    fallback = project_root / "config" / "nicknames.yaml"
    return fallback if fallback.is_file() else configured


@lru_cache
def get_chat_nicknames() -> tuple[str, ...]:
    return tuple(load_nicknames(resolve_nicknames_path()).values())


def find_nicknames_in_text(text: str) -> list[str]:
    normalized_text = _normalize(text)
    if not normalized_text:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for nickname in get_chat_nicknames():
        normalized_name = _normalize(nickname)
        if len(normalized_name) < 3:
            continue
        matched = (
            normalized_name in normalized_text
            or any(
                token.startswith(normalized_name)
                for token in normalized_text.split()
            )
        )
        if matched and normalized_name not in seen:
            seen.add(normalized_name)
            found.append(nickname)
    return found


def format_nicknames_for_planner() -> str:
    nicknames = get_chat_nicknames()
    if not nicknames:
        return "(не заданы)"
    return ", ".join(sorted(nicknames, key=str.lower))
