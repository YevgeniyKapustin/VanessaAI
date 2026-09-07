"""VRChat speaker identity: join overlay or a new name-keyed card, never fuzzy."""

from __future__ import annotations

from dataclasses import dataclass

from vanessa.knowledge.format import slugify
from vanessa.knowledge.people.people import canonicalize_person
from vanessa.knowledge.people.people_identity import normalize_person_text
from vanessa.knowledge.people.vrchat_joins import load_vrchat_joins
from vanessa.knowledge.users.roster import canonical_name_for_telegram_id


@dataclass(frozen=True, slots=True)
class PersonCard:
    """Resolved People card. ``telegram_id`` is set only by an explicit join."""

    person_id: str
    telegram_id: int | None = None


def _entry_id(value: object) -> str:
    if isinstance(value, dict):
        note_id = value.get("id")
        if note_id is not None:
            return str(note_id)
    return ""


def _id_from_telegram_map(telegram_id: int, people_index: dict | None) -> str:
    telegram_map = (people_index or {}).get("telegram_id")
    if not isinstance(telegram_map, dict):
        return ""
    return _entry_id(telegram_map.get(str(telegram_id)))


def _telegram_bound_ids(people_index: dict | None) -> set[str]:
    telegram_map = (people_index or {}).get("telegram_id")
    if not isinstance(telegram_map, dict):
        return set()
    return {_entry_id(entry) for entry in telegram_map.values()} - {""}


def _card_id_for_telegram(telegram_id: int, people_index: dict | None) -> str:
    from_index = _id_from_telegram_map(telegram_id, people_index)
    if from_index:
        return from_index
    nickname = canonical_name_for_telegram_id(telegram_id)
    if nickname:
        return slugify(nickname)
    return f"user-{telegram_id}"


def _joined_card(telegram_id: int, people_index: dict | None) -> PersonCard:
    return PersonCard(
        person_id=_card_id_for_telegram(telegram_id, people_index),
        telegram_id=telegram_id,
    )


def _name_keyed_card(display_name: str, people_index: dict | None) -> PersonCard:
    person_id = slugify(display_name)
    if person_id in _telegram_bound_ids(people_index):
        person_id = f"{person_id}-vrchat"
    return PersonCard(person_id=person_id)


def resolve_vrchat_speaker(
    display_name: str,
    people_index: dict | None = None,
    *,
    joins: dict[str, int] | None = None,
) -> PersonCard:
    """Map a VRChat display name to a People card without fuzzy merge.

    1. Overlay join by normalized display name → existing card for that
       ``telegram_id``.
    2. Else a new name-keyed id (``slugify``), ``telegram_id`` empty.
    3. Never ``identity_similar`` / alias-fuzzy. Two Alexes stay two cards.
    """
    reference = normalize_person_text(display_name)
    if not reference:
        return PersonCard("")
    table = joins if joins is not None else load_vrchat_joins()
    telegram_id = table.get(reference)
    if telegram_id is not None:
        return _joined_card(telegram_id, people_index)
    return _name_keyed_card(display_name, people_index)


def resolve_person_card(
    person: str,
    telegram_id: int | None,
    people_index: dict | None,
    *,
    channel: str | None = None,
) -> PersonCard:
    """Channel dispatch: VRChat uses the join/name resolver, TG stays as today."""
    if (channel or "") == "vrchat":
        return resolve_vrchat_speaker(person, people_index)
    return PersonCard(person_id=canonicalize_person(person, telegram_id, people_index))
