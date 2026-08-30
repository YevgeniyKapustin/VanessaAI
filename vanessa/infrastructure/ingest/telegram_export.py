from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ParsedExportMessage:
    telegram_message_id: int
    sender_telegram_id: int | None
    sender_display_name: str | None
    content: str
    created_at: datetime


def export_id_to_chat_id(chat_type: str, export_id: int) -> int:
    if chat_type in {
        "private_supergroup",
        "public_supergroup",
        "supergroup",
        "private_channel",
        "public_channel",
    }:
        if export_id > 0:
            return int(f"-100{export_id}")
        return export_id
    if chat_type in {"private_group", "group"}:
        if export_id > 0:
            return -export_id
        return export_id
    return export_id


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            parts.append(str(item.get("text", "")))
    return "".join(parts).strip()


def parse_sender_id(from_id: Any) -> int | None:
    if from_id is None:
        return None
    if isinstance(from_id, int):
        return from_id
    if not isinstance(from_id, str):
        return None
    digits = "".join(ch for ch in from_id if ch.isdigit())
    if not digits:
        return None
    return int(digits)


def _parse_sender_display_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.strip()
    return name or None


def parse_datetime(value: str) -> datetime:
    from datetime import timezone

    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def parse_telegram_export(path: Path) -> tuple[dict[str, Any], list[ParsedExportMessage]]:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    messages: list[ParsedExportMessage] = []
    for item in data.get("messages", []):
        if item.get("type") != "message":
            continue
        content = flatten_text(item.get("text"))
        if not content:
            continue
        messages.append(
            ParsedExportMessage(
                telegram_message_id=int(item["id"]),
                sender_telegram_id=parse_sender_id(item.get("from_id")),
                sender_display_name=_parse_sender_display_name(item.get("from")),
                content=content,
                created_at=parse_datetime(item["date"]),
            )
        )

    messages.sort(key=lambda message: message.created_at)
    return data, messages


def extract_sender_names_from_export(path: Path) -> dict[int, str]:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    counts: dict[int, Counter[str]] = defaultdict(Counter)
    for item in data.get("messages", []):
        if item.get("type") != "message":
            continue
        telegram_id = parse_sender_id(item.get("from_id"))
        display_name = _parse_sender_display_name(item.get("from"))
        if telegram_id is None or display_name is None:
            continue
        counts[telegram_id][display_name] += 1

    return {
        telegram_id: name_counts.most_common(1)[0][0]
        for telegram_id, name_counts in counts.items()
    }
