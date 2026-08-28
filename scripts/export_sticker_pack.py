#!/usr/bin/env python
"""Dump the bot's Telegram sticker pack to fill config/content/stickers.yaml.

Usage:
    python scripts/export_sticker_pack.py [set_name]            # print-only
    python scripts/export_sticker_pack.py [set_name] --update   # rewrite file_ids/indices

Prints one line per sticker:
    index=<n> emoji=<e> file_id=<id>

With ``--update`` the script also rewrites ``file_id`` / ``index`` of every
sticker already present in config/content/stickers.yaml (matched by ``index`` or
``emoji``), preserving the rest of the file, and reports pack stickers that are
not yet in the config so you can add them. The default set name comes from the
config.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import httpx
import yaml

from app.config.content import get_content, resolve_content_source
from app.config.settings import settings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print the sticker pack and optionally refresh file_ids in the config.",
    )
    parser.add_argument(
        "set_name",
        nargs="?",
        default=get_content().stickers.sticker_set_name,
        help="Sticker set short name, e.g. VanessaBot",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Rewrite file_id/index of known stickers in config/content/stickers.yaml",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --update: print what would change without writing the file",
    )
    return parser


def _resolve_stickers_yaml() -> Path:
    """Locate the stickers config file (single-file or per-section directory)."""
    source = resolve_content_source()
    if source.is_dir():
        return source / "stickers.yaml"
    return source


def _parse_name(stripped: str) -> str:
    value = stripped.split(":", 1)[1].strip()
    return value.strip("\"'").strip()


def _rewrite_block(block: list[str], index: int, file_id: str) -> list[str]:
    """Return the sticker block with index/file_id set, inserting file_id if absent."""
    out: list[str] = []
    had_file_id = False
    for line in block:
        stripped = line.strip()
        if stripped.startswith("index:"):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}index: {index}\n")
            continue
        if stripped.startswith("file_id:"):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f'{indent}file_id: "{file_id}"\n')
            had_file_id = True
            continue
        out.append(line)
    if not had_file_id:
        # Insert file_id right after the index line (fall back to emoji line).
        for pos, line in enumerate(out):
            if line.strip().startswith("index:"):
                indent = line[: len(line) - len(line.lstrip())]
                out.insert(pos + 1, f'{indent}file_id: "{file_id}"\n')
                break
        else:
            for pos, line in enumerate(out):
                if line.strip().startswith("emoji:"):
                    indent = line[: len(line) - len(line.lstrip())]
                    out.insert(pos + 1, f'{indent}file_id: "{file_id}"\n')
                    break
    return out


def apply_updates_to_text(text: str, updates: dict[str, tuple[int, str]]) -> str:
    """Rewrite index/file_id inside the yaml by name, preserving all other content."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("- name:"):
            name = _parse_name(stripped)
            base_indent = len(line) - len(line.lstrip())
            block = [line]
            i += 1
            while i < n:
                nxt = lines[i]
                if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= base_indent:
                    break
                block.append(nxt)
                i += 1
            if name in updates:
                index, file_id = updates[name]
                out.extend(_rewrite_block(block, index, file_id))
            else:
                out.extend(block)
            continue
        out.append(line)
        i += 1
    return "".join(out)


def build_updates(data: dict, remote: list[dict]) -> dict[str, tuple[int, str]]:
    """Compute index/file_id updates for known stickers and report pack changes."""
    by_index = {r["index"]: r for r in remote}
    by_emoji = {r["emoji"]: r for r in remote}
    updates: dict[str, tuple[int, str]] = {}
    matched_remote: set[int] = set()

    for item in data.get("stickers", []):
        name = item.get("name")
        match = None
        idx = item.get("index")
        if idx is not None and idx in by_index:
            match = by_index[idx]
        if match is None and item.get("emoji") in by_emoji:
            match = by_emoji[item["emoji"]]
        if match is None:
            print(f"MISSING in pack: name={name} index={idx!r} emoji={item.get('emoji')!r}")
            continue
        matched_remote.add(match["index"])
        old_id = item.get("file_id")
        new_id = match["file_id"]
        new_index = match["index"]
        if old_id != new_id or item.get("index") != new_index:
            updates[name] = (new_index, new_id)
            old_desc = old_id if old_id else "<missing>"
            print(f"UPDATE name={name} index={item.get('index')!r}->{new_index} "
                  f"file_id={old_desc}->{new_id}")
        else:
            print(f"OK name={name} index={new_index} file_id={new_id}")

    new_pack = [r for r in remote if r["index"] not in matched_remote]
    for r in new_pack:
        print(
            f"NEW in pack (not in config): index={r['index']} "
            f"emoji={r['emoji']!r} file_id={r['file_id']}"
        )
    return updates


def main() -> None:
    args = build_parser().parse_args()

    token = settings.telegram_bot_token.strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        raise SystemExit(1)

    response = httpx.post(
        f"https://api.telegram.org/bot{token}/getStickerSet",
        json={"name": args.set_name},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        print(f"API error: {data.get('description')}", file=sys.stderr)
        raise SystemExit(1)

    stickers = data.get("result", {}).get("stickers", [])
    remote = [
        {"index": index, "emoji": sticker.get("emoji", ""), "file_id": sticker.get("file_id", "")}
        for index, sticker in enumerate(stickers)
    ]
    print(f"set_name={args.set_name} stickers={len(stickers)}")

    if not args.update:
        for r in remote:
            print(
                f"index={r['index']} "
                f"emoji={r['emoji'].encode('unicode_escape').decode('ascii')!r} "
                f"file_id={r['file_id']}"
            )
        return

    yaml_path = _resolve_stickers_yaml()
    print(f"sticker_config={yaml_path}")
    config = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    updates = build_updates(config, remote)
    if not updates:
        print("No file_id/index changes needed.")
        return
    if args.dry_run:
        print("dry_run: skipping write")
        return

    text = yaml_path.read_text(encoding="utf-8")
    yaml_path.write_text(apply_updates_to_text(text, updates), encoding="utf-8")
    print(f"Updated {len(updates)} sticker(s) in {yaml_path}")


if __name__ == "__main__":
    main()
