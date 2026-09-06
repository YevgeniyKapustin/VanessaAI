"""CLI helpers for ``scripts/merge_people.py``."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from scripts.merge_people_apply import delete_card, merge_cards
from scripts.merge_people_cards import Card, Group, Review
from vanessa.config.settings import settings
from vanessa.knowledge.format import PEOPLE, slugify
from vanessa.knowledge.index import KnowledgeIndex
from vanessa.knowledge.store.vault import KnowledgeVault


def _print_auto_groups(groups: list[Group]) -> None:
    if not groups:
        return
    print(f"AUTO ({len(groups)} — applied by --apply --yes):")
    for group in groups:
        print(f"  merge into {group.target}: {', '.join(group.sources)}")
        for reason in group.reasons:
            print(f"      {reason}")


def _print_reviews(reviews: list[Review]) -> None:
    if not reviews:
        return
    print(f"\nREVIEW ({len(reviews)} — apply with --merge SRC:TGT):")
    for review in reviews:
        print(f"  merge into {review.target}: {', '.join(review.sources)}")
        print(f"      {review.reason}")


def _print_suspicious(suspicious: list[tuple[str, str]]) -> None:
    if not suspicious:
        return
    print(f"\nSUSPICIOUS ({len(suspicious)} — not merged; needs a decision):")
    for card_id, note in suspicious:
        print(f"  {card_id}: {note}")


def print_plan(
    groups: list[Group],
    reviews: list[Review],
    suspicious: list[tuple[str, str]],
    people: dict[str, Card],
    roster: dict[int, str],
) -> None:
    print("=== People card merge plan ===\n")
    if not groups and not reviews:
        print("No duplicate cards detected.")
    _print_auto_groups(groups)
    _print_reviews(reviews)
    _print_suspicious(suspicious)
    roster_slugs = sorted({slugify(nickname) for nickname in roster.values()})
    missing = [slug for slug in roster_slugs if slug not in people]
    if missing:
        print(f"\nRoster members without a People card: {', '.join(missing)}")


async def rebuild_indexes(root: Path) -> None:
    vault = KnowledgeVault(root_path=str(root))
    index = KnowledgeIndex(vault)
    await index.rebuild_folder(PEOPLE)
    print("rebuilt People/_index.yaml")


def knowledge_root() -> Path | None:
    raw_root = (settings.knowledge_path or "").strip()
    if not raw_root:
        print("KNOWLEDGE_PATH is not set")
        return None
    return Path(raw_root).resolve()


def _preview_only(args: argparse.Namespace) -> bool:
    if args.dry_run:
        return True
    return not args.apply


def _confirmed_apply(args: argparse.Namespace) -> bool:
    return bool(args.yes or args.merge or args.delete)


def _apply_merges(
    people: dict[str, Card],
    groups: list[Group],
    args: argparse.Namespace,
) -> None:
    print("=== Applying merge plan ===")
    for group in groups:
        merge_cards(people, group.target, group.sources)
    for spec in args.merge:
        source, target = spec.split(":", 1)
        merge_cards(people, target, [source])
    for card_id in args.delete:
        delete_card(people, card_id)


def _apply_if_confirmed(
    args: argparse.Namespace,
    people: dict[str, Card],
    groups: list[Group],
    root: Path,
) -> int:
    if not _confirmed_apply(args):
        print("Nothing to do; pass --yes (and/or --merge/--delete) to confirm.")
        return 0
    _apply_merges(people, groups, args)
    asyncio.run(rebuild_indexes(root))
    return 0


def run_merge_cli(
    args: argparse.Namespace,
    root: Path,
    people: dict[str, Card],
    groups: list[Group],
    reviews: list[Review],
    suspicious: list[tuple[str, str]],
    roster: dict[int, str],
) -> int:
    if args.reindex:
        asyncio.run(rebuild_indexes(root))
        return 0
    if _preview_only(args):
        print_plan(groups, reviews, suspicious, people, roster)
        return 0
    return _apply_if_confirmed(args, people, groups, root)
