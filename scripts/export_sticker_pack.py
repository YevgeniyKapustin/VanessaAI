#!/usr/bin/env python
"""Dump the bot's Telegram sticker pack to fill config/behavior/humor/stickers.yaml.

Usage:
    python scripts/export_sticker_pack.py [set_name]            # print-only
    python scripts/export_sticker_pack.py [set_name] --update   # rewrite file_ids/indices

Prints one line per sticker:
    index=<n> emoji=<e> file_id=<id>

With ``--update`` the script also rewrites ``file_id`` / ``index`` of every
sticker already present in config/behavior/humor/stickers.yaml (matched by ``index`` or
``emoji``), preserving the rest of the file, and reports pack stickers that are
not yet in the config so you can add them. The default set name comes from the
config.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from scripts.export_sticker_pack_ops import (
    fetch_remote_stickers,
    match_sticker,
    print_new_in_pack,
    print_pack_listing,
    record_match,
    require_token,
    write_updates,
)
from vanessa.config.content import (
    CONTENT_SECTIONS,
    get_content,
    resolve_content_source,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

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
        help="Rewrite file_id/index of known stickers in config/behavior/humor/stickers.yaml",
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
        relative = CONTENT_SECTIONS["stickers"]
        if isinstance(relative, tuple):
            relative = relative[0]
        return source / relative
    return source


def build_updates(data: dict, remote: list[dict]) -> dict[str, tuple[int, str]]:
    """Compute index/file_id updates for known stickers and report pack changes."""
    by_index = {r["index"]: r for r in remote}
    by_emoji = {r["emoji"]: r for r in remote}
    updates: dict[str, tuple[int, str]] = {}
    matched_remote: set[int] = set()

    for item in data.get("stickers", []):
        match = match_sticker(item, by_index, by_emoji)
        if match is None:
            print(
                f"MISSING in pack: name={item.get('name')} "
                f"index={item.get('index')!r} emoji={item.get('emoji')!r}"
            )
            continue
        record_match(item, match, updates, matched_remote)

    print_new_in_pack(remote, matched_remote)
    return updates


def main() -> None:
    args = build_parser().parse_args()
    token = require_token()
    remote = fetch_remote_stickers(token, args.set_name)
    print(f"set_name={args.set_name} stickers={len(remote)}")
    if not args.update:
        print_pack_listing(remote)
        return

    yaml_path = _resolve_stickers_yaml()
    print(f"sticker_config={yaml_path}")
    config = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    updates = build_updates(config, remote)
    write_updates(yaml_path, updates, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
