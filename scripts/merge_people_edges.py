"""Identity and telegram edges for People-card merge groups."""

from __future__ import annotations

from scripts.merge_people_cards import Card
from vanessa.knowledge.format import slugify
from vanessa.knowledge.people import identity_key, identity_similar

_MIN_GROUP_SIZE = 2


def _telegram_pairs(members: list[str]) -> list[tuple[str, str]]:
    return [(a, b) for a in members for b in members if a < b]


def _telegram_reason(telegram_id: int, nickname: str | None) -> str:
    if nickname is None:
        return f"same unknown telegram_id {telegram_id}"
    return f"same telegram_id {telegram_id} («{nickname}»)"


def _should_link_telegram(
    a: str,
    b: str,
    nickname: str | None,
    roster_slug: str | None,
    affiliates: dict[str, str | None],
) -> bool:
    if nickname is None:
        return True
    return affiliates[a] == roster_slug and affiliates[b] == roster_slug


def _roster_slug(nickname: str | None) -> str | None:
    if nickname is None:
        return None
    return slugify(nickname)


def add_telegram_edges_for_id(
    telegram_id: int,
    members: list[str],
    roster: dict[int, str],
    affiliates: dict[str, str | None],
    add_edge,
) -> None:
    if len(members) < _MIN_GROUP_SIZE:
        return
    nickname = roster.get(telegram_id)
    roster_slug = _roster_slug(nickname)
    for a, b in _telegram_pairs(members):
        if _should_link_telegram(a, b, nickname, roster_slug, affiliates):
            add_edge(a, b, _telegram_reason(telegram_id, nickname))


def link_shared_telegram(
    people: dict[str, Card],
    roster: dict[int, str],
    affiliates: dict[str, str | None],
    add_edge,
) -> None:
    by_telegram: dict[int, list[str]] = {}
    for card_id, card in people.items():
        if card.telegram_id is not None:
            by_telegram.setdefault(card.telegram_id, []).append(card_id)
    for telegram_id, members in by_telegram.items():
        add_telegram_edges_for_id(
            telegram_id, members, roster, affiliates, add_edge
        )


def _roster_conflict(
    affiliates: dict[str, str | None], a: str, b: str
) -> bool:
    return bool(affiliates[a] and affiliates[b] and affiliates[a] != affiliates[b])


def _identity_reason(card_a: Card, card_b: Card) -> str | None:
    keys_a = {identity_key(alias) for alias in card_a.aliases}
    keys_b = {identity_key(alias) for alias in card_b.aliases}
    shared = keys_a & keys_b
    if shared:
        return f"identical identity key {min(shared)!r}"
    if _aliases_similar(card_a, card_b):
        return "similar transliterated identity"
    return None


def _aliases_similar(card_a: Card, card_b: Card) -> bool:
    return any(
        identity_similar(x, y) for x in card_a.aliases for y in card_b.aliases
    )


def _try_link_pair(
    a: str,
    b: str,
    people: dict[str, Card],
    affiliates: dict[str, str | None],
    add_edge,
) -> None:
    if a >= b:
        return
    if _roster_conflict(affiliates, a, b):
        return
    reason = _identity_reason(people[a], people[b])
    if reason is None:
        return
    add_edge(a, b, reason)


def link_identities(
    ids: list[str],
    people: dict[str, Card],
    affiliates: dict[str, str | None],
    add_edge,
) -> None:
    for a in ids:
        for b in ids:
            _try_link_pair(a, b, people, affiliates, add_edge)
