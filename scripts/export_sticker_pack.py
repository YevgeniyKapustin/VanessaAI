#!/usr/bin/env python
"""Dump the bot's Telegram sticker pack to fill config/content/stickers.yaml.

Usage:
    python scripts/export_sticker_pack.py [set_name]

Prints one line per sticker:
    index=<n> emoji=<e> file_id=<id>

Copy `index` (or, if the runtime fetch is restricted, `file_id`) into the matching
entry of config/content/stickers.yaml. The default set name comes from the config.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import httpx

from app.config.content import get_content
from app.config.settings import settings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print the sticker pack so you can map stickers to tags.",
    )
    parser.add_argument(
        "set_name",
        nargs="?",
        default=get_content().stickers.sticker_set_name,
        help="Sticker set short name, e.g. VanessaBot",
    )
    return parser


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
    print(f"set_name={args.set_name} stickers={len(stickers)}")
    for index, sticker in enumerate(stickers):
        # Escape the emoji so the output survives any console encoding (cp1252 etc.).
        emoji = sticker.get("emoji", "")
        emoji_escaped = emoji.encode("unicode_escape").decode("ascii")
        print(
            f"index={index} "
            f"emoji={emoji_escaped!r} "
            f"file_id={sticker.get('file_id', '')}"
        )


if __name__ == "__main__":
    main()
