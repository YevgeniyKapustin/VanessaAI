"""Detect duplicate People cards and propose merge groups."""

from __future__ import annotations

from scripts.merge_people_cards import (
    Card,
    Group,
    Review,
    _affiliation,
    _body_line_count,
    _has_cyrillic,
)
from scripts.merge_people_edges import link_identities, link_shared_telegram

_MIN_GROUP_SIZE = 2


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


def _reasons_for_members(
    members: list[str],
    reasons: dict[tuple[str, str], list[str]],
) -> list[str]:
    member_set = set(members)
    group_reasons: list[str] = []
    for (a, b), rs in reasons.items():
        if a in member_set and b in member_set:
            group_reasons.extend(rs)
    return list(dict.fromkeys(group_reasons))


def _group_from_members(
    members: list[str],
    people: dict[str, Card],
    affiliates: dict[str, str | None],
    reasons: dict[tuple[str, str], list[str]],
) -> Group:
    target = _pick_target(members, people, affiliates)
    sources = [member for member in members if member != target]
    return Group(
        target=target,
        sources=sources,
        reasons=_reasons_for_members(members, reasons),
        auto=True,
    )


def _groups_from_components(
    ids: list[str],
    union_find: _UnionFind,
    reasons: dict[tuple[str, str], list[str]],
    people: dict[str, Card],
    affiliates: dict[str, str | None],
) -> list[Group]:
    components: dict[str, list[str]] = {}
    for card_id in ids:
        components.setdefault(union_find.find(card_id), []).append(card_id)

    groups: list[Group] = []
    for members in components.values():
        if len(members) < _MIN_GROUP_SIZE:
            continue
        groups.append(_group_from_members(members, people, affiliates, reasons))
    groups.sort(key=lambda group: (group.target, group.sources))
    return groups


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

    link_shared_telegram(people, roster, affiliates, add_edge)
    link_identities(ids, people, affiliates, add_edge)
    groups = _groups_from_components(
        ids, union_find, reasons, people, affiliates
    )
    reviews: list[Review] = []
    suspicious = sorted(conflicts.items())

    return groups, reviews, suspicious
