from services.bot.stickers.decider import StickerDecider
from services.bot.stickers.models import StickerCatalog, StickerDef


class _Rng:
    """Deterministic stand-in for random.Random used by the decider."""

    def __init__(self, value: float) -> None:
        self._value = value

    def random(self) -> float:
        return self._value

    def choices(self, population, weights=None, *, k=1, cum_weights=None):
        return [population[0]]


def _catalog() -> StickerCatalog:
    return StickerCatalog(
        set_name="test",
        stickers=[
            StickerDef(
                name="eyes_roll",
                tags=("sarcasm", "disapproval"),
                resolved_file_id="f:sarcasm",
            ),
            StickerDef(
                name="hype",
                tags=("delight",),
                resolved_file_id="f:delight",
            ),
            StickerDef(
                name="hi",
                tags=("greeting",),
                resolved_file_id="f:greeting",
            ),
            StickerDef(
                name="shrug",
                tags=("shrug",),
                resolved_file_id="f:shrug",
            ),
        ],
    )


def _decider(**kwargs) -> StickerDecider:
    kwargs.setdefault("catalog", _catalog())
    kwargs.setdefault("rng", _Rng(0.0))
    kwargs.setdefault("probability", 1.0)
    kwargs.setdefault("heuristic_probability", 1.0)
    return StickerDecider(**kwargs)


def test_first_reply_may_carry_a_sticker():
    decider = _decider()
    pick = decider.decide(1, tag="sarcasm")
    assert pick is not None
    assert pick.tag == "sarcasm"
    assert pick.file_id == "f:sarcasm"


def test_cooldown_blocks_until_enough_replies():
    decider = _decider(min_messages_between=10)
    assert decider.decide(1, tag="sarcasm") is not None

    # after a sticker the counter resets; 5 replies is not enough yet
    decider.register_sticker(1)
    for _ in range(5):
        decider.register_reply(1)
    assert decider.decide(1, tag="sarcasm") is None

    # after 10 replies since the sticker the sticker is allowed again
    for _ in range(5):
        decider.register_reply(1)
    assert decider.messages_since_sticker(1) == 10
    assert decider.decide(1, tag="sarcasm") is not None


def test_probability_gate():
    blocked = _decider(rng=_Rng(0.5), probability=0.35)
    assert blocked.decide(1, tag="sarcasm") is None

    passed = _decider(rng=_Rng(0.2), probability=0.35)
    assert passed.decide(1, tag="sarcasm") is not None


def test_llm_tag_preferred_over_heuristics():
    decider = _decider()
    # reply text says "greeting", but the LLM explicitly tagged sarcasm
    pick = decider.decide(1, tag="sarcasm", reply_text="Ну привет!")
    assert pick is not None
    assert pick.tag == "sarcasm"


def test_heuristic_fallback_when_no_llm_tag():
    decider = _decider()
    pick = decider.decide(1, reply_text="Ну привет!")
    assert pick is not None
    assert pick.tag == "greeting"


def test_no_signal_returns_none():
    decider = _decider()
    assert decider.decide(1, reply_text="обычное сообщение") is None


def test_disabled_returns_none():
    decider = _decider(enabled=False)
    assert decider.decide(1, tag="sarcasm") is None


def test_empty_catalog_returns_none():
    catalog = StickerCatalog(
        set_name="test",
        stickers=[StickerDef(name="a", tags=("x",))],
    )
    decider = _decider(catalog=catalog)
    assert decider.decide(1, tag="sarcasm") is None


def test_counter_starts_eligible():
    decider = _decider(min_messages_between=10)
    assert decider.messages_since_sticker(1) == 10
    decider.register_reply(1)
    assert decider.messages_since_sticker(1) == 11


def test_force_bypasses_cooldown():
    decider = _decider(min_messages_between=10)
    # put the chat deep into cooldown
    decider.register_sticker(1)
    for _ in range(5):
        decider.register_reply(1)
    assert decider.decide(1, tag="sarcasm") is None
    pick = decider.decide(1, tag="sarcasm", force=True)
    assert pick is not None
    assert pick.tag == "sarcasm"


def test_force_bypasses_probability_gate():
    blocked = _decider(rng=_Rng(0.5), probability=0.35)
    assert blocked.decide(1, tag="sarcasm") is None
    pick = blocked.decide(1, tag="sarcasm", force=True)
    assert pick is not None
    assert pick.tag == "sarcasm"


def test_force_sends_random_sticker_when_no_tag():
    decider = _decider()
    assert decider.decide(1, reply_text="обычное сообщение") is None
    pick = decider.decide(1, reply_text="обычное сообщение", force=True)
    assert pick is not None
    assert pick.file_id == "f:sarcasm"  # _Rng.choices picks the first candidate


def test_force_still_skips_when_disabled():
    decider = _decider(enabled=False)
    assert decider.decide(1, tag="sarcasm", force=True) is None


def test_force_still_skips_when_no_files():
    catalog = StickerCatalog(
        set_name="test",
        stickers=[StickerDef(name="a", tags=("x",))],
    )
    decider = _decider(catalog=catalog)
    assert decider.decide(1, tag="sarcasm", force=True) is None


def test_per_tag_probability_raises_chance():
    # base probability low, but the tag override is high
    decider = _decider(rng=_Rng(0.5), probability=0.2, tag_probability={"delight": 0.9})
    pick = decider.decide(1, tag="delight")
    assert pick is not None
    assert pick.tag == "delight"


def test_per_tag_probability_lowers_chance():
    # base probability high, but the tag override is low
    blocked = _decider(rng=_Rng(0.5), probability=0.9, tag_probability={"delight": 0.3})
    assert blocked.decide(1, tag="delight") is None

    passed = _decider(rng=_Rng(0.2), probability=0.9, tag_probability={"delight": 0.3})
    assert passed.decide(1, tag="delight") is not None


def test_per_tag_probability_falls_back_for_other_tags():
    # override only exists for delight; sarcasm uses the base probability
    decider = _decider(rng=_Rng(0.5), probability=1.0, tag_probability={"delight": 0.1})
    pick = decider.decide(1, tag="sarcasm")
    assert pick is not None
    assert pick.tag == "sarcasm"


def test_per_tag_probability_is_case_insensitive():
    decider = _decider(rng=_Rng(0.5), probability=0.2, tag_probability={"delight": 0.9})
    pick = decider.decide(1, tag="DELIGHT")
    assert pick is not None
    assert pick.tag == "delight"
