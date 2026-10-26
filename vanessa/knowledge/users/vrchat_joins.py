"""Explicit VRChat identities from People-card metadata and its index."""

from __future__ import annotations


def normalize_vrchat_name(name: str) -> str:
    return " ".join(name.replace("ё", "е").lower().split())


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
        key = normalize_vrchat_name(name)
        if key:
            mapping[key] = telegram_id


def parse_vrchat_joins(raw: object) -> dict[str, int]:
    """Read ``vrchat_names`` and ``telegram_id`` from People-card metadata."""
    if not isinstance(raw, list):
        return {}
    mapping: dict[str, int] = {}
    for item in raw:
        if isinstance(item, dict):
            _record_join(mapping, item)
    return mapping


def vrchat_joins_from_index(people_index: dict | None) -> dict[str, int]:
    mapping = (people_index or {}).get("vrchat_names")
    return mapping if isinstance(mapping, dict) else {}
