#!/usr/bin/env python
"""Propose and apply merges for duplicate People cards in the knowledge vault.

The memory LLM sometimes created several People cards for the same participant
(Latin transliterations, mixed Latin/Cyrillic homoglyphs, extra aliases). This
tool builds a merge plan from strong identity signals, prints it in dry-run
mode, and merges (metrics live in the person cards) in apply mode.

Usage:
    python scripts/merge_people.py --dry-run
    python scripts/merge_people.py --apply --yes
    python scripts/merge_people.py --apply --yes --merge "dup-slug:canonical-slug"
    python scripts/merge_people.py --apply --yes --delete "junk-slug"

Tiers shown by --dry-run:
    AUTO        high confidence (shared telegram_id, identical identity key,
                similar transliteration). Applied by --apply --yes.
    SUSPICIOUS  telegram_id vs identity conflicts; merge or delete by hand.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

with contextlib.suppress(AttributeError):
    sys.stdout.reconfigure(encoding="utf-8")

from scripts.merge_people_apply import (  # noqa: E402, F401
    delete_card,
    merge_bodies,
    merge_cards,
    split_sections,
)
from scripts.merge_people_cards import load_people  # noqa: E402
from scripts.merge_people_cli import knowledge_root, run_merge_cli  # noqa: E402
from scripts.merge_people_groups import detect_groups  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the plan (default)")
    parser.add_argument("--apply", action="store_true", help="apply the merge plan")
    parser.add_argument("--yes", action="store_true", help="confirm the apply")
    parser.add_argument(
        "--merge",
        action="append",
        default=[],
        metavar="SRC:TGT",
        help="additionally merge card SRC into card TGT",
    )
    parser.add_argument(
        "--delete",
        action="append",
        default=[],
        metavar="ID",
        help="delete a card entirely (e.g. a pseudo-person)",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="only rebuild People/_index.yaml",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = knowledge_root()
    if root is None:
        return 1
    people = load_people(root)
    roster = {
        card.telegram_id: str(card.meta.get("nickname") or card.id)
        for card in people.values()
        if card.telegram_id is not None
    }
    groups, reviews, suspicious = detect_groups(people, roster)
    return run_merge_cli(args, root, people, groups, reviews, suspicious, roster)


if __name__ == "__main__":
    raise SystemExit(main())
