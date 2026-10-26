from vanessa.knowledge.index.index_build import build_people_index
from vanessa.knowledge.people.people import canonicalize_person
from vanessa.knowledge.people.people_identity import (
    identity_similar,
    normalize_person_text,
)
from vanessa.knowledge.people.vrchat_speaker import (
    resolve_person_card,
    resolve_vrchat_speaker,
)
from vanessa.knowledge.schema import VaultNote
from vanessa.knowledge.users.vrchat_joins import parse_vrchat_joins

KAPUSTA_TG = 7714154251
ALEX_TG = 42


def _index(person_id: str, telegram_id: int, *aliases: str) -> dict:
    entry = {"id": person_id, "file": f"People/{person_id}.md"}
    return {
        "telegram_id": {str(telegram_id): entry},
        "aliases": {alias.lower(): entry for alias in aliases},
    }


def test_identical_display_names_without_join_are_two_cards() -> None:
    index = _index("alex", ALEX_TG, "Alex")
    telegram = canonicalize_person("Alex", ALEX_TG, index)
    vrchat = resolve_vrchat_speaker("Alex", index, joins={})
    assert telegram == "alex"
    assert vrchat.person_id != telegram
    assert vrchat.telegram_id is None


def test_explicit_join_collapses_to_one_card() -> None:
    index = _index("евгений-капуста", KAPUSTA_TG, "Евгений (Капуста)", "Капуста")
    joins = {
        normalize_person_text("Капуста"): KAPUSTA_TG,
        normalize_person_text("Kapusta"): KAPUSTA_TG,
    }
    cyrillic = resolve_vrchat_speaker("Капуста", index, joins=joins)
    latin = resolve_vrchat_speaker("Kapusta", index, joins=joins)
    assert cyrillic.person_id == latin.person_id == "евгений-капуста"
    assert cyrillic.telegram_id == latin.telegram_id == KAPUSTA_TG


def test_fuzzy_does_not_merge_vrchat_names() -> None:
    index = _index("евгений-капуста", KAPUSTA_TG, "Евгений (Капуста)", "Капуста")
    assert identity_similar("Kapusta", "Капуста")
    merged = canonicalize_person("Kapusta", None, index)
    vrchat = resolve_vrchat_speaker("Kapusta", index, joins={})
    assert merged == "евгений-капуста"
    assert vrchat.person_id != merged
    assert vrchat.telegram_id is None


def test_people_card_binds_yevgeniy_to_telegram() -> None:
    note = VaultNote(
        "People/owner.md",
        meta={"id": "owner", "telegram_id": ALEX_TG, "vrchat_names": ["Yevgeniy"]},
    )
    card = resolve_vrchat_speaker("Yevgeniy", build_people_index([note]))
    assert card.person_id == "owner"
    assert card.telegram_id == ALEX_TG


def test_parse_joins_skips_invalid_rows() -> None:
    table = parse_vrchat_joins(
        [
            {"telegram_id": "nope", "vrchat_names": ["X"]},
            {"vrchat_names": ["Y"]},
            {"telegram_id": KAPUSTA_TG, "vrchat_names": ["Капуста", ""]},
        ]
    )
    assert table == {normalize_person_text("Капуста"): KAPUSTA_TG}


def test_blank_display_name_is_empty_card() -> None:
    assert resolve_vrchat_speaker("  ", joins={}).person_id == ""


def test_roster_is_not_reverse_vrchat_lookup() -> None:
    card = resolve_vrchat_speaker("Крабер", {}, joins={})
    assert card.telegram_id is None
    assert card.person_id == "крабер"


def test_resolve_person_card_dispatches_on_channel() -> None:
    index = _index("alex", ALEX_TG, "Alex")
    tg = resolve_person_card("Alex", ALEX_TG, index, channel="telegram")
    vr = resolve_person_card("Alex", None, index, channel="vrchat")
    assert tg.person_id == "alex"
    assert vr.person_id != tg.person_id


def test_join_without_index_falls_back_to_user_slug() -> None:
    fallback_id = 999001
    joins = {normalize_person_text("Newbie"): fallback_id}
    card = resolve_vrchat_speaker("Newbie", {"telegram_id": "bad"}, joins=joins)
    assert card.telegram_id == fallback_id
    assert card.person_id.startswith("user-") or card.person_id


def test_joined_card_uses_index_when_present() -> None:
    index = _index("евгений-капуста", KAPUSTA_TG, "Капуста")
    joins = {normalize_person_text("Kapusta"): KAPUSTA_TG}
    card = resolve_vrchat_speaker("Kapusta", index, joins=joins)
    assert card.person_id == "евгений-капуста"


def test_parse_joins_skips_non_list_and_non_positive() -> None:
    assert parse_vrchat_joins("nope") == {}
    table = parse_vrchat_joins(
        [
            {"telegram_id": 0, "vrchat_names": ["Zero"]},
            {"telegram_id": KAPUSTA_TG, "vrchat_names": "not-a-list"},
        ]
    )
    assert table == {}


def test_invalid_index_binding_keeps_vrchat_card_separate() -> None:
    card = resolve_vrchat_speaker("Alex", {"vrchat_names": "bad"})
    assert card.person_id == "alex"
    assert card.telegram_id is None


def test_people_card_edit_replaces_vrchat_binding() -> None:
    note = VaultNote(
        "People/owner.md",
        meta={"id": "owner", "telegram_id": ALEX_TG, "vrchat_names": ["OldName"]},
    )
    before = build_people_index([note])
    note.meta["vrchat_names"] = ["Yevgeniy"]
    after = build_people_index([note])
    assert resolve_vrchat_speaker("OldName", before).telegram_id == ALEX_TG
    assert resolve_vrchat_speaker("OldName", after).telegram_id is None
    assert resolve_vrchat_speaker("Yevgeniy", after).telegram_id == ALEX_TG


def test_entry_id_skips_non_dict_index_values() -> None:
    index = {"telegram_id": {str(ALEX_TG): "not-a-dict"}}
    card = resolve_vrchat_speaker(
        "Alex",
        index,
        joins={normalize_person_text("Alex"): ALEX_TG},
    )
    assert card.telegram_id == ALEX_TG
