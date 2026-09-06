"""Helpers for sticker-pack dump and config file_id refresh."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

from scripts.export_sticker_yaml import apply_updates_to_text
from vanessa.config.settings import settings


def require_token() -> str:
    token = settings.telegram_bot_token.strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        raise SystemExit(1)
    return token


def fetch_remote_stickers(token: str, set_name: str) -> list[dict]:
    response = httpx.post(
        f"https://api.telegram.org/bot{token}/getStickerSet",
        json={"name": set_name},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        print(f"API error: {data.get('description')}", file=sys.stderr)
        raise SystemExit(1)
    stickers = data.get("result", {}).get("stickers", [])
    return [
        {
            "index": index,
            "emoji": sticker.get("emoji", ""),
            "file_id": sticker.get("file_id", ""),
        }
        for index, sticker in enumerate(stickers)
    ]


def print_pack_listing(remote: list[dict]) -> None:
    for row in remote:
        print(
            f"index={row['index']} "
            f"emoji={row['emoji'].encode('unicode_escape').decode('ascii')!r} "
            f"file_id={row['file_id']}"
        )


def match_sticker(
    item: dict,
    by_index: dict,
    by_emoji: dict,
) -> dict | None:
    idx = item.get("index")
    if idx is not None and idx in by_index:
        return by_index[idx]
    if item.get("emoji") in by_emoji:
        return by_emoji[item["emoji"]]
    return None


def _file_id_desc(old_id: object) -> object:
    if old_id:
        return old_id
    return "<missing>"


def record_match(
    item: dict,
    match: dict,
    updates: dict[str, tuple[int, str]],
    matched_remote: set[int],
) -> None:
    name = item.get("name")
    matched_remote.add(match["index"])
    old_id = item.get("file_id")
    new_id = match["file_id"]
    new_index = match["index"]
    if old_id != new_id or item.get("index") != new_index:
        updates[name] = (new_index, new_id)
        old_desc = _file_id_desc(old_id)
        print(
            f"UPDATE name={name} index={item.get('index')!r}->{new_index} "
            f"file_id={old_desc}->{new_id}"
        )
        return
    print(f"OK name={name} index={new_index} file_id={new_id}")


def print_new_in_pack(remote: list[dict], matched_remote: set[int]) -> None:
    for row in remote:
        if row["index"] in matched_remote:
            continue
        print(
            f"NEW in pack (not in config): index={row['index']} "
            f"emoji={row['emoji']!r} file_id={row['file_id']}"
        )


def write_updates(
    yaml_path: Path,
    updates: dict[str, tuple[int, str]],
    *,
    dry_run: bool,
) -> None:
    if not updates:
        print("No file_id/index changes needed.")
        return
    if dry_run:
        print("dry_run: skipping write")
        return
    text = yaml_path.read_text(encoding="utf-8")
    yaml_path.write_text(apply_updates_to_text(text, updates), encoding="utf-8")
    print(f"Updated {len(updates)} sticker(s) in {yaml_path}")
