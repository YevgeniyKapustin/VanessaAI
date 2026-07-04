import pytest

from app.llm.profanity_substitution import ProfanitySubstitutor

_LEMMAS = {
    "блин": "блядь",
    "чёрт": "блядь",
    "капец": "пиздец",
    "фиг": "хуй",
    "фигня": "хуйня",
    "задолбать": "заебать",
    "бесить": "заебывать",
}
_INVARIABLE = {
    "ёлки": "нахуй",
    "ёлки-палки": "нахуй",
}


@pytest.fixture
def substitutor() -> ProfanitySubstitutor:
    return ProfanitySubstitutor(
        lemmas=_LEMMAS,
        invariable=_INVARIABLE,
        enabled=True,
    )


def test_disabled_returns_original():
    service = ProfanitySubstitutor(lemmas=_LEMMAS, enabled=False)
    assert service.apply("Да блин") == "Да блин"


def test_preserves_word_boundaries(substitutor: ProfanitySubstitutor):
    assert substitutor.apply("неблин") == "неблин"


def test_invariable_phrases(substitutor: ProfanitySubstitutor):
    assert substitutor.apply("Ёлки-палки!") == "Нахуй!"
    assert substitutor.apply("да ёлки") == "да нахуй"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("блин", "блядь"),
        ("Блин", "Блядь"),
        ("блином", "блядью"),
        ("блина", "бляди"),
        ("чёрта", "бляди"),
        ("капец", "пиздец"),
        ("капецу", "пиздецу"),
        ("фиг", "хуй"),
        ("фигу", "хую"),
        ("фигня", "хуйня"),
        ("фигней", "хуйней"),
        ("задолбало", "заебало"),
        ("задолбали", "заебали"),
        ("задолбать", "заебать"),
        ("бесит", "заебывает"),
        ("бесило", "заебывало"),
    ],
)
def test_morphological_replacement(
    substitutor: ProfanitySubstitutor,
    source: str,
    expected: str,
):
    assert substitutor.apply(source) == expected


def test_sentence_with_multiple_tokens(substitutor: ProfanitySubstitutor):
    result = substitutor.apply("Да блин, это капец, задолбали уже")
    assert "бляд" in result
    assert "пиздец" in result
    assert "заебали" in result
