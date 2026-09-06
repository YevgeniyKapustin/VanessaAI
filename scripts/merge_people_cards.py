"""People card records loaded from the knowledge vault."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vanessa.knowledge.format import PEOPLE, parse_frontmatter, slugify
from vanessa.knowledge.people import identity_similar


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


def _aliases_match_nickname(card: Card, nickname: str) -> bool:
    return any(identity_similar(alias, nickname) for alias in card.aliases)


def _affiliation_from_telegram(
    card: Card, roster: dict[int, str]
) -> tuple[str | None, str | None] | None:
    if card.telegram_id is None:
        return None
    if card.telegram_id not in roster:
        return None
    nickname = roster[card.telegram_id]
    roster_slug = slugify(nickname)
    if _aliases_match_nickname(card, nickname):
        return roster_slug, None
    return None, (
        f"telegram_id {card.telegram_id} is «{nickname}» but the identity doesn't match"
    )


def _affiliation_from_aliases(
    card: Card, roster: dict[int, str]
) -> tuple[str | None, str | None]:
    for nickname in roster.values():
        if _aliases_match_nickname(card, nickname):
            return slugify(nickname), None
    return None, None


def _affiliation(card: Card, roster: dict[int, str]) -> tuple[str | None, str | None]:
    """Canonical roster slug this card belongs to, plus a conflict note if any."""
    from_tg = _affiliation_from_telegram(card, roster)
    if from_tg is not None:
        return from_tg
    return _affiliation_from_aliases(card, roster)


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
