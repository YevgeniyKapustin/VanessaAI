"""Merge and delete People cards on disk."""

from __future__ import annotations

from pathlib import Path

from scripts.merge_people_cards import Card
from vanessa.knowledge.format import render_note, today


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


def _merge_section_lines(
    merged: dict[str, list[str]],
    order: list[str],
    heading: str,
    lines: list[str],
) -> None:
    if heading not in merged:
        merged[heading] = []
        order.append(heading)
    seen = {line.strip() for line in merged[heading]}
    for line in lines:
        if line.strip() and line.strip() not in seen:
            merged[heading].append(line)
            seen.add(line.strip())


def _collect_sections(
    bodies: list[str],
) -> tuple[dict[str, list[str]], list[str]]:
    merged: dict[str, list[str]] = {}
    order: list[str] = []
    for body in bodies:
        if not body:
            continue
        for heading, lines in split_sections(body):
            _merge_section_lines(merged, order, heading, lines)
    return merged, order


def _nonempty_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if line.strip()]


def _append_section(parts: list[str], heading: str, lines: list[str]) -> None:
    if not heading and not lines:
        return
    if heading:
        parts.append(heading)
    parts.extend(lines)


def _render_sections(merged: dict[str, list[str]], order: list[str]) -> str:
    parts: list[str] = []
    for heading in order:
        _append_section(parts, heading, _nonempty_lines(merged[heading]))
    return "\n".join(parts)


def merge_bodies(bodies: list[str]) -> str:
    merged, order = _collect_sections(bodies)
    return _render_sections(merged, order)


def _merge_metrics(*metrics: object) -> dict:
    merged: dict = {}
    for block in metrics:
        if isinstance(block, dict):
            merged = {**merged, **block}
    return merged


def _absorb_aliases(meta: dict, aliases: list[str]) -> None:
    for alias in aliases:
        if alias not in meta["aliases"]:
            meta["aliases"].append(alias)


def _older_created(created: object, source_created: object) -> object:
    if source_created and (not created or str(source_created) < str(created)):
        return source_created
    return created


def _copy_missing_keys(meta: dict, source_meta: dict) -> None:
    for key in ("names", "mood", "section"):
        value = source_meta.get(key)
        if value is not None and key not in meta:
            meta[key] = value


def _fill_telegram_id(meta: dict, telegram_id: int | None) -> None:
    if meta.get("telegram_id") is None and telegram_id is not None:
        meta["telegram_id"] = telegram_id


def _require_card(people: dict[str, Card], card_id: str, *, kind: str) -> Card:
    if card_id not in people:
        raise SystemExit(f"{kind} card not found: {card_id}")
    return people[card_id]


def _absorb_source(meta: dict, created: object, source_card: Card) -> object:
    _absorb_aliases(meta, source_card.aliases)
    _fill_telegram_id(meta, source_card.telegram_id)
    created = _older_created(created, source_card.meta.get("created"))
    _copy_missing_keys(meta, source_card.meta)
    return created


def _attach_metrics_and_telegram(
    meta: dict,
    target_card: Card,
    source_cards: list[Card],
) -> None:
    metrics = _merge_metrics(
        *[card.meta.get("metrics") for card in source_cards],
        target_card.meta.get("metrics"),
    )
    if metrics:
        meta["metrics"] = metrics
    if target_card.telegram_id is not None:
        meta["telegram_id"] = target_card.telegram_id


def _build_merged_meta(
    target_card: Card,
    source_cards: list[Card],
    target: str,
) -> dict:
    meta: dict = {"type": "person", "id": target, "aliases": list(target_card.aliases)}
    created = target_card.meta.get("created")
    for source_card in source_cards:
        created = _absorb_source(meta, created, source_card)
    if created:
        meta["created"] = created
    meta["updated"] = today()
    _attach_metrics_and_telegram(meta, target_card, source_cards)
    return meta


def _delete_sources(people: dict[str, Card], sources: list[str]) -> None:
    for source in sources:
        source_card = people[source]
        _delete_files(people_path=source_card.path)
        print(f"  deleted People/{source}.md")


def merge_cards(
    people: dict[str, Card],
    target: str,
    sources: list[str],
) -> None:
    target_card = _require_card(people, target, kind="target")
    source_cards = [_require_card(people, source, kind="source") for source in sources]
    meta = _build_merged_meta(target_card, source_cards, target)
    body = merge_bodies([target_card.body] + [card.body for card in source_cards])
    target_card.path.write_text(render_note(meta, body), encoding="utf-8")
    print(f"  merged {len(sources) + 1} card(s) -> {target}")
    _delete_sources(people, sources)


def delete_card(people: dict[str, Card], card_id: str) -> None:
    if card_id not in people:
        raise SystemExit(f"card not found: {card_id}")
    _delete_files(people_path=people[card_id].path)
    print(f"  deleted People/{card_id}.md")


def _delete_files(*, people_path: Path) -> None:
    if people_path.exists():
        people_path.unlink()
