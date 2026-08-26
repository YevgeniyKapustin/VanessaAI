from app.llm.memes import MemeDecider


class _Rng:
    """Deterministic stand-in for random.Random used by the decider."""

    def __init__(self, value: float) -> None:
        self._value = value

    def random(self) -> float:
        return self._value


def _decider(**kwargs) -> MemeDecider:
    kwargs.setdefault("rng", _Rng(0.0))
    kwargs.setdefault("probability", 1.0)
    return MemeDecider(**kwargs)


def test_first_reply_may_offer_a_meme():
    decider = _decider()
    assert decider.decide(1) is True


def test_cooldown_blocks_until_enough_replies():
    decider = _decider(min_messages_between=10)
    assert decider.decide(1) is True

    # after a meme the counter resets; 5 replies is not enough yet
    decider.register_meme(1)
    for _ in range(5):
        decider.register_reply(1)
    assert decider.decide(1) is False

    # after 10 replies since the meme it is allowed again
    for _ in range(5):
        decider.register_reply(1)
    assert decider.messages_since_meme(1) == 10
    assert decider.decide(1) is True


def test_probability_gate():
    blocked = _decider(rng=_Rng(0.5), probability=0.35)
    assert blocked.decide(1) is False

    passed = _decider(rng=_Rng(0.2), probability=0.35)
    assert passed.decide(1) is True


def test_disabled_returns_false():
    decider = _decider(enabled=False)
    assert decider.decide(1) is False


def test_counter_is_per_chat():
    decider = _decider(min_messages_between=3)
    decider.register_meme(1)
    decider.register_reply(1)
    assert decider.decide(1) is False
    # another chat is still eligible
    assert decider.decide(2) is True


def test_counter_starts_eligible():
    decider = _decider(min_messages_between=10)
    assert decider.messages_since_meme(1) == 10
    decider.register_reply(1)
    assert decider.messages_since_meme(1) == 11
