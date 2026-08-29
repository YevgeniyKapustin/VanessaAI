#!/usr/bin/env python
"""Build .env.local from an existing monolith .env.

Copies secrets and values that differ from .env.defaults. Skips placeholders,
VISION_PHOTO_PLACEHOLDER, and Anthropic keys unless LLM_PROVIDER=claude.

    python scripts/prepare_env.py
    python scripts/prepare_env.py --from .env --dry-run
    python scripts/prepare_env.py --force
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.config.env_overlay import prepare_local_overlay, render_overlay


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create .env.local from a current .env overlay",
    )
    parser.add_argument(
        "--from",
        dest="source",
        type=Path,
        default=None,
        help="Source env (default: project .env)",
    )
    parser.add_argument(
        "--to",
        dest="destination",
        type=Path,
        default=None,
        help="Output overlay (default: project .env.local)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the destination if it already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the overlay and do not write",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        overlay, dest = prepare_local_overlay(
            _PROJECT_ROOT,
            source=args.source,
            destination=args.destination,
        )
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    text = render_overlay(overlay)
    if args.dry_run:
        print(text, end="")
        return 0
    if dest.exists() and not args.force:
        print(
            f"{dest} already exists; pass --force to overwrite",
            file=sys.stderr,
        )
        return 1
    dest.write_text(text, encoding="utf-8")
    print(f"wrote {dest} ({len(overlay)} keys)")
    print(
        "run: docker compose --env-file .env.defaults "
        "--env-file .env.local up -d --build"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
