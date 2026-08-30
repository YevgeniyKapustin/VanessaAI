from vanessa.config.content import MemeDefContent, MemesContent
from vanessa.pipeline.llm.memes import MemeCatalog


def _content(**kwargs) -> MemesContent:
    defaults: dict = {
        "enabled": True,
        "probability": 0.4,
        "min_messages_between": 8,
        "max_per_reply": 1,
        "offer_on_humor": True,
        "offer_max": 6,
        "memes": [
            MemeDefContent(
                name="Окак",
                keywords=["окаешь", "окает"],
                meaning="недоумение на абсурд",
                usage="абсурдная ситуация",
            ),
            MemeDefContent(
                name="Смерть в нищете",
                keywords=["смерть в нищете", "нищета", "страх бедности"],
                meaning="страх бедности",
                usage="деньги и кризис",
            ),
        ],
    }
    defaults.update(kwargs)
    return MemesContent(**defaults)


def _catalog(**kwargs) -> MemeCatalog:
    return MemeCatalog(_content(**kwargs))


def test_no_keyword_hit_returns_empty():
    catalog = _catalog()
    assert catalog.match("просто привет") == []


def test_empty_message_returns_empty():
    catalog = _catalog()
    assert catalog.match("") == []
    assert catalog.match("   ") == []


def test_keyword_match_is_case_insensitive():
    catalog = _catalog()
    assert [meme.name for meme in catalog.match("ОКАЕШЬ")] == ["Окак"]
    assert [meme.name for meme in catalog.match("окаешь")] == ["Окак"]


def test_whole_word_avoids_false_positives():
    catalog = _catalog()
    # «окаешь» must not match inside «пока» or «оказывается»
    assert catalog.match("пока") == []
    assert catalog.match("оказывается") == []


def test_multiword_phrase_matches():
    catalog = _catalog()
    assert [meme.name for meme in catalog.match("опять смерть в нищете")] == [
        "Смерть в нищете"
    ]


def test_max_results_limits_matches():
    catalog = _catalog(max_per_reply=1)
    names = [meme.name for meme in catalog.match("нищета окаешь")]
    # catalog order, capped at the default max_per_reply
    assert names == ["Окак"]

    names = [meme.name for meme in catalog.match("нищета окаешь", max_results=2)]
    assert names == ["Окак", "Смерть в нищете"]


def test_properties_expose_gate_settings():
    catalog = _catalog(
        enabled=False,
        probability=0.2,
        min_messages_between=5,
        max_per_reply=2,
    )
    assert catalog.enabled is False
    assert catalog.probability == 0.2
    assert catalog.min_messages_between == 5
    assert catalog.max_per_reply == 2


def test_offer_properties_expose_config():
    catalog = _catalog(offer_on_humor=False, offer_max=3)
    assert catalog.offer_on_humor is False
    assert catalog.offer_max == 3


def test_offerable_rotates_across_calls():
    memes = [
        MemeDefContent(name=name, keywords=[name])
        for name in ["a", "b", "c", "d", "e"]
    ]
    catalog = MemeCatalog(MemesContent(memes=memes, offer_max=2))
    assert [meme.name for meme in catalog.offerable()] == ["a", "b"]
    assert [meme.name for meme in catalog.offerable()] == ["c", "d"]
    assert [meme.name for meme in catalog.offerable()] == ["e", "a"]


def test_offerable_caps_to_catalog_size():
    catalog = _catalog(offer_max=10)  # only 2 memes exist
    offered = catalog.offerable()
    assert len(offered) == 2
    assert offered[0].name == "Окак"


def test_offerable_handles_empty_catalog():
    catalog = MemeCatalog(MemesContent(memes=[], offer_max=5))
    assert catalog.offerable() == []
