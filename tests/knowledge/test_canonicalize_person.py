from vanessa.knowledge.people.people import canonicalize_person

KAPUSTA_TG = 7714154251


def _index(person_id: str, telegram_id: int, *aliases: str) -> dict:
    entry = {"id": person_id, "file": f"People/{person_id}.md"}
    return {
        "telegram_id": {str(telegram_id): entry},
        "aliases": {alias.lower(): entry for alias in aliases},
    }


def test_canonicalize_resolves_telegram_id_to_existing_card() -> None:
    index = _index("евгений-капуста", KAPUSTA_TG, "Евгений (Капуста)", "Капуста")
    assert canonicalize_person("ignored", KAPUSTA_TG, index) == "евгений-капуста"


def test_canonicalize_fuzzy_merges_alias_without_telegram_id() -> None:
    index = _index("евгений-капуста", KAPUSTA_TG, "Евгений (Капуста)", "Капуста")
    assert canonicalize_person("Kapusta", None, index) == "евгений-капуста"


def test_canonicalize_blank_reference_is_empty() -> None:
    assert canonicalize_person("  ", None, {}) == ""
