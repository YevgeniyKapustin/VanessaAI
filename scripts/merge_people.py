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
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.config.settings import settings
from app.ingest.user_backfill import load_nicknames
from app.knowledge.format import (
    PEOPLE,
    parse_frontmatter,
    render_note,
    slugify,
    today,
)
from app.knowledge.index import KnowledgeIndex
from app.knowledge.people import identity_key, identity_similar
from app.knowledge.vault import KnowledgeVault

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # pragma: no cover - Python < 3.7
    pass


@dataclass
class Card:
    id: str
    path: Path
    aliases: list[str]
    telegram_id: int | None
    meta: dict
    body: str


@dataclass
class Group:
    target: str
    sources: list[str]
    reasons: list[str] = field(default_factory=list)
    auto: bool = True


@dataclass
class Review:
    target: str
    sources: list[str]
    reason: str


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _has_cyrillic(text: str) -> bool:
    return any("\u0400" <= char <= "\u04ff" for char in text)


def _body_line_count(card: Card) -> int:
    return sum(1 for line in card.body.splitlines() if line.strip())


def _affiliation(card: Card, roster: dict[int, str]) -> tuple[str | None, str | None]:
    """Canonical roster slug this card belongs to, plus a conflict note if any."""
    if card.telegram_id is not None and card.telegram_id in roster:
        nickname = roster[card.telegram_id]
        roster_slug = slugify(nickname)
        if any(identity_similar(alias, nickname) for alias in card.aliases):
            return roster_slug, None
        return None, (
            f"telegram_id {card.telegram_id} is «{nickname}» but the identity doesn't match"
        )
    for nickname in roster.values():
        if any(identity_similar(alias, nickname) for alias in card.aliases):
            return slugify(nickname), None
    return None, None


class _UnionFind:
    def __init__(self, ids: list[str]) -> None:
        self._parent = {item: item for item in ids}

    def find(self, item: str) -> str:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


def load_people(root: Path) -> dict[str, Card]:
    cards: dict[str, Card] = {}
    people_dir = root / PEOPLE
    for md in sorted(people_dir.glob("*.md")):
        meta, body = parse_frontmatter(md.read_text(encoding="utf-8"))
        card_id = str(meta.get("id") or slugify(md.stem))
        aliases = _as_list(meta.get("aliases")) + _as_list(meta.get("names")) + [card_id]
        aliases = list(
            dict.fromkeys(str(alias).strip() for alias in aliases if str(alias).strip())
        )
        raw_tg = meta.get("telegram_id")
        telegram_id = None
        if raw_tg is not None:
            try:
                telegram_id = int(raw_tg)
            except (TypeError, ValueError):
                telegram_id = None
        cards[card_id] = Card(
            id=card_id,
            path=md,
            aliases=aliases,
            telegram_id=telegram_id,
            meta=meta,
            body=body,
        )
    return cards


def _pick_target(
    members: list[str],
    people: dict[str, Card],
    affiliates: dict[str, str | None],
) -> str:
    # 1) the card whose id equals its canonical roster slug.
    for member in members:
        if affiliates.get(member) == member:
            return member
    # 2) prefer the Cyrillic spelling over a Latin transliteration.
    cyrillic = [member for member in members if _has_cyrillic(member)]
    if len(cyrillic) == 1:
        return cyrillic[0]
    # 3) the richest card, then a stable order.
    return max(
        members,
        key=lambda member: (member in cyrillic, _body_line_count(people[member])),
    )


def detect_groups(
    people: dict[str, Card],
    roster: dict[int, str],
) -> tuple[list[Group], list[Review], list[tuple[str, str]]]:
    ids = list(people)
    union_find = _UnionFind(ids)
    reasons: dict[tuple[str, str], list[str]] = {}

    def add_edge(a: str, b: str, reason: str) -> None:
        union_find.union(a, b)
        key = tuple(sorted((a, b)))
        reasons.setdefault(key, []).append(reason)

    affiliates: dict[str, str | None] = {}
    conflicts: dict[str, str] = {}
    for card_id, card in people.items():
        affiliate, conflict = _affiliation(card, roster)
        affiliates[card_id] = affiliate
        if conflict:
            conflicts[card_id] = conflict

    # Telegram-id edges (strongest signal). Guarded: a card whose telegram id
    # contradicts its own identity (e.g. «владислав» claiming Зонов's id) is
    # never merged through that id.
    by_telegram: dict[int, list[str]] = {}
    for card_id, card in people.items():
        if card.telegram_id is not None:
            by_telegram.setdefault(card.telegram_id, []).append(card_id)
    for telegram_id, members in by_telegram.items():
        if len(members) < 2:
            continue
        nickname = roster.get(telegram_id)
        for a in members:
            for b in members:
                if a >= b:
                    continue
                if nickname is not None:
                    roster_slug = slugify(nickname)
                    if affiliates[a] == roster_slug and affiliates[b] == roster_slug:
                        add_edge(a, b, f"same telegram_id {telegram_id} («{nickname}»)")
                else:
                    add_edge(a, b, f"same unknown telegram_id {telegram_id}")

    # Identity edges: exact transliterated key, or fuzzy similarity. Guarded so
    # two distinct roster members with similar names (e.g. two «Алексей») never
    # merge.
    for a in ids:
        for b in ids:
            if a >= b:
                continue
            card_a, card_b = people[a], people[b]
            if (
                affiliates[a]
                and affiliates[b]
                and affiliates[a] != affiliates[b]
            ):
                continue
            keys_a = {identity_key(alias) for alias in card_a.aliases}
            keys_b = {identity_key(alias) for alias in card_b.aliases}
            shared = keys_a & keys_b
            if shared:
                add_edge(a, b, f"identical identity key {sorted(shared)[0]!r}")
            elif any(
                identity_similar(x, y) for x in card_a.aliases for y in card_b.aliases
            ):
                add_edge(a, b, "similar transliterated identity")

    components: dict[str, list[str]] = {}
    for card_id in ids:
        components.setdefault(union_find.find(card_id), []).append(card_id)

    groups: list[Group] = []
    for members in components.values():
        if len(members) < 2:
            continue
        member_set = set(members)
        group_reasons: list[str] = []
        for (a, b), rs in reasons.items():
            if a in member_set and b in member_set:
                group_reasons.extend(rs)
        target = _pick_target(members, people, affiliates)
        sources = [member for member in members if member != target]
        groups.append(
            Group(
                target=target,
                sources=sources,
                reasons=list(dict.fromkeys(group_reasons)),
                auto=True,
            )
        )
    groups.sort(key=lambda group: (group.target, group.sources))

    reviews: list[Review] = []
    suspicious = sorted(conflicts.items())

    return groups, reviews, suspicious


def split_sections(body: str) -> list[tuple[str, list[str]]]:
    """[(heading, lines)] preserving order; heading == "" for preamble lines."""
    sections: list[tuple[str, list[str]]] = []
    heading = ""
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("## "):
            sections.append((heading, lines))
            heading = stripped
            lines = []
        else:
            lines.append(line)
    sections.append((heading, lines))
    return sections


def merge_bodies(bodies: list[str]) -> str:
    merged: dict[str, list[str]] = {}
    order: list[str] = []
    for body in bodies:
        if not body:
            continue
        for heading, lines in split_sections(body):
            if heading not in merged:
                merged[heading] = []
                order.append(heading)
            seen = {line.strip() for line in merged[heading]}
            for line in lines:
                if line.strip() and line.strip() not in seen:
                    merged[heading].append(line)
                    seen.add(line.strip())
    parts: list[str] = []
    for heading in order:
        lines = [line for line in merged[heading] if line.strip()]
        if not heading and not lines:
            continue
        if heading:
            parts.append(heading)
        parts.extend(lines)
    return "\n".join(parts)


def _merge_metrics(*metrics: object) -> dict:
    merged: dict = {}
    for block in metrics:
        if isinstance(block, dict):
            merged = {**merged, **block}
    return merged


def merge_cards(
    people: dict[str, Card],
    target: str,
    sources: list[str],
    root: Path,
) -> None:
    if target not in people:
        raise SystemExit(f"target card not found: {target}")
    target_card = people[target]
    meta: dict = {"type": "person", "id": target, "aliases": list(target_card.aliases)}
    created = target_card.meta.get("created")
    for source in sources:
        if source not in people:
            raise SystemExit(f"source card not found: {source}")
        source_card = people[source]
        for alias in source_card.aliases:
            if alias not in meta["aliases"]:
                meta["aliases"].append(alias)
        if meta.get("telegram_id") is None and source_card.telegram_id is not None:
            meta["telegram_id"] = source_card.telegram_id
        source_created = source_card.meta.get("created")
        if source_created and (not created or str(source_created) < str(created)):
            created = source_created
        for key in ("names", "mood", "section"):
            value = source_card.meta.get(key)
            if value is not None and key not in meta:
                meta[key] = value
    if created:
        meta["created"] = created
    meta["updated"] = today()
    metrics = _merge_metrics(
        *[people[source].meta.get("metrics") for source in sources],
        target_card.meta.get("metrics"),
    )
    if metrics:
        meta["metrics"] = metrics
    if target_card.telegram_id is not None:
        meta["telegram_id"] = target_card.telegram_id

    body = merge_bodies([target_card.body] + [people[source].body for source in sources])
    target_card.path.write_text(render_note(meta, body), encoding="utf-8")
    print(f"  merged {len(sources) + 1} card(s) -> {target}")

    for source in sources:
        source_card = people[source]
        _delete_files(source_card.id, root, people_path=source_card.path)
        print(f"  deleted People/{source}.md")


def delete_card(people: dict[str, Card], card_id: str, root: Path) -> None:
    if card_id not in people:
        raise SystemExit(f"card not found: {card_id}")
    _delete_files(card_id, root, people_path=people[card_id].path)
    print(f"  deleted People/{card_id}.md")


def _delete_files(card_id: str, root: Path, *, people_path: Path) -> None:
    if people_path.exists():
        people_path.unlink()


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
    if groups:
        print(f"AUTO ({len(groups)} — applied by --apply --yes):")
        for group in groups:
            print(f"  merge into {group.target}: {', '.join(group.sources)}")
            for reason in group.reasons:
                print(f"      {reason}")
    if reviews:
        print(f"\nREVIEW ({len(reviews)} — apply with --merge SRC:TGT):")
        for review in reviews:
            print(f"  merge into {review.target}: {', '.join(review.sources)}")
            print(f"      {review.reason}")
    if suspicious:
        print(f"\nSUSPICIOUS ({len(suspicious)} — not merged; needs a decision):")
        for card_id, note in suspicious:
            print(f"  {card_id}: {note}")
    roster_slugs = sorted({slugify(nickname) for nickname in roster.values()})
    missing = [slug for slug in roster_slugs if slug not in people]
    if missing:
        print(f"\nRoster members without a People card: {', '.join(missing)}")


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


async def _rebuild_indexes(root: Path) -> None:
    vault = KnowledgeVault(root_path=str(root))
    index = KnowledgeIndex(vault)
    await index.rebuild_folder(PEOPLE)
    print("rebuilt People/_index.yaml")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    raw_root = (settings.knowledge_path or "").strip()
    if not raw_root:
        print("KNOWLEDGE_PATH is not set")
        return 1
    root = Path(raw_root).resolve()
    people = load_people(root)
    roster = load_nicknames(Path(settings.nicknames_config_path))
    groups, reviews, suspicious = detect_groups(people, roster)

    if args.reindex:
        asyncio.run(_rebuild_indexes(root))
        return 0

    if not args.apply or args.dry_run:
        print_plan(groups, reviews, suspicious, people, roster)
        return 0

    if not (args.yes or args.merge or args.delete):
        print("Nothing to do; pass --yes (and/or --merge/--delete) to confirm.")
        return 0

    print("=== Applying merge plan ===")
    for group in groups:
        merge_cards(people, group.target, group.sources, root)
    for spec in args.merge:
        source, target = spec.split(":", 1)
        merge_cards(people, target, [source], root)
    for card_id in args.delete:
        delete_card(people, card_id, root)

    asyncio.run(_rebuild_indexes(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
