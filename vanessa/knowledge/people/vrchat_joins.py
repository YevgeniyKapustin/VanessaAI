"""Overlay: VRChat display names bound to an existing People card."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from vanessa.config.paths import resolve_settings_path
from vanessa.config.settings import settings
from vanessa.knowledge.people.people_identity import normalize_person_text


def resolve_joins_path() -> Path:
    return resolve_settings_path(settings.joins_config_path, "joins.yaml")


def _positive_int(raw: object) -> int | None:
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def _name_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(name).strip() for name in raw if str(name).strip()]


def _record_join(mapping: dict[str, int], item: dict) -> None:
    telegram_id = _positive_int(item.get("telegram_id"))
    if telegram_id is None:
        return
    for name in _name_list(item.get("vrchat_names")):
        key = normalize_person_text(name)
        if key:
            mapping[key] = telegram_id


def parse_vrchat_joins(raw: object) -> dict[str, int]:
    """Parse joins.yaml into ``normalized display name -> telegram_id``."""
    if not isinstance(raw, list):
        return {}
    mapping: dict[str, int] = {}
    for item in raw:
        if isinstance(item, dict):
            _record_join(mapping, item)
    return mapping


def _read_joins(path: Path) -> object:
    if not path.is_file():
        return []
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


@lru_cache
def load_vrchat_joins() -> dict[str, int]:
    return parse_vrchat_joins(_read_joins(resolve_joins_path()))


def clear_vrchat_joins_cache() -> None:
    load_vrchat_joins.cache_clear()
