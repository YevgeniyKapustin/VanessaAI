from vanessa.core.bot_senders import bot_sender_label, is_bot_sender_label
from vanessa.pipeline.decision.bot_peer_budget import BotPeerBudget, BotPeerLimits

CHAT = "telegram:-100"
KIRILL = 777


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _budget(**limits) -> tuple[BotPeerBudget, Clock]:
    clock = Clock()
    return BotPeerBudget(BotPeerLimits(**limits), clock=clock), clock


def test_reply_loop_stops_at_depth_limit():
    budget, clock = _budget(max_in_row=3, cooldown_seconds=0)
    for _ in range(3):
        assert budget.allows(CHAT, KIRILL)
        budget.record_reply(CHAT, KIRILL)
        clock.now += 1
    assert budget.blocked_reason(CHAT, KIRILL) == "depth"


def test_depth_count_resets_after_human_message():
    budget, _ = _budget(max_in_row=2, cooldown_seconds=0)
    budget.record_reply(CHAT, KIRILL, count=2)
    assert budget.blocked_reason(CHAT, KIRILL) == "depth"
    budget.note_human("telegram:-200")
    assert budget.blocked_reason(CHAT, KIRILL) == "depth"
    budget.note_human(CHAT)
    assert budget.allows(CHAT, KIRILL)


def test_cooldown_blocks_fast_bot_then_expires():
    budget, clock = _budget(cooldown_seconds=10)
    budget.record_reply(CHAT, KIRILL)
    clock.now += 9.9
    assert budget.blocked_reason(CHAT, KIRILL) == "cooldown"
    assert budget.allows(CHAT, 888)
    clock.now += 0.2
    assert budget.allows(CHAT, KIRILL)


def test_hourly_cap_counts_all_bots_in_chat():
    budget, clock = _budget(max_in_row=0, cooldown_seconds=0, max_per_hour=3)
    budget.record_reply(CHAT, KIRILL, count=2)
    budget.record_reply(CHAT, 888)
    assert budget.blocked_reason(CHAT, 999) == "hourly"
    assert budget.allows("telegram:-200", 999)
    clock.now += 3600
    assert budget.allows(CHAT, 999)


def test_zero_limits_turn_checks_off():
    budget, _ = _budget(max_in_row=0, cooldown_seconds=0, max_per_hour=0)
    budget.record_reply(CHAT, KIRILL, count=50)
    assert budget.allows(CHAT, KIRILL)


def test_default_limits_match_owner_numbers():
    limits = BotPeerLimits()
    assert (limits.max_in_row, limits.cooldown_seconds, limits.max_per_hour) == (
        3,
        10.0,
        20,
    )


def test_bot_sender_label_is_idempotent():
    label = bot_sender_label("@Kirill")
    assert label == "[бот Kirill]"
    assert bot_sender_label(label) == label
    assert bot_sender_label(None) == "[бот без имени]"
    assert is_bot_sender_label(label)
    assert not is_bot_sender_label("Кирилл")
    assert not is_bot_sender_label(None)
