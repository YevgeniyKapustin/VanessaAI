"""VaultNote <-> knowledge_nodes row conversion helpers."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Any

from vanessa.knowledge.schema import VaultNote


def try_int(item: object) -> int | None:
    try:
        return int(item)
    except (TypeError, ValueError):
        return None


def as_int_list(value: object) -> list[int]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    result: list[int] = []
    seen: set[int] = set()
    for item in items:
        _append_unique_int(result, seen, item)
    return result


def _append_unique_int(result: list[int], seen: set[int], item: object) -> None:
    number = try_int(item)
    if number is None:
        return
    if number in seen:
        return
    seen.add(number)
    result.append(number)


def date_from_text(text: str, fallback: date) -> date:
    if not text:
        return fallback
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return fallback


def parse_date(value: object, fallback: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date_from_text(str(value or "").strip(), fallback)


def _optional_iso_date(value: object) -> str | None:
    if value is None:
        return None
    return value.date().isoformat()


def _as_dict(value: object) -> dict:
    if not value:
        return {}
    return dict(value)


def _str_or(value: object, fallback: str) -> str:
    if value:
        return str(value)
    return fallback


def _as_list(value: object) -> list:
    if not value:
        return []
    return list(value)


def _put_if_truthy(meta: dict[str, Any], key: str, value: object) -> None:
    if value:
        meta[key] = value


def _apply_sources(meta: dict[str, Any], row: Any) -> None:
    sources = _as_list(getattr(row, "source_message_ids", None))
    if not sources:
        return
    meta["source_message_ids"] = [int(item) for item in sources]


def _apply_row_dates(meta: dict[str, Any], row: Any) -> None:
    created = _optional_iso_date(getattr(row, "created_at", None))
    if created is not None:
        meta["created"] = created
    updated = _optional_iso_date(getattr(row, "updated_at", None))
    if updated is not None:
        meta["updated"] = updated


def _row_frontmatter(row: Any) -> dict[str, Any]:
    extra = _as_dict(getattr(row, "metadata_", None))
    slug = _str_or(getattr(row, "slug", None), PurePosixPath(row.id).stem)
    node_type = _str_or(getattr(row, "type", None), "note")
    meta: dict[str, Any] = {**extra, "id": slug, "type": node_type}
    _put_if_truthy(meta, "title", getattr(row, "title", None))
    _put_if_truthy(meta, "aliases", _as_list(getattr(row, "aliases", None)))
    _apply_sources(meta, row)
    _apply_row_dates(meta, row)
    return meta


def row_to_note(row: Any) -> VaultNote:
    """Rebuild a ``VaultNote`` from a ``knowledge_nodes`` row."""
    meta = _row_frontmatter(row)
    updated_at = getattr(row, "updated_at", None)
    epoch = updated_at.timestamp() if updated_at is not None else 0.0
    return VaultNote(
        relative_path=str(row.id),
        meta=meta,
        body=str(getattr(row, "content", None) or ""),
        updated_at=epoch,
    )
