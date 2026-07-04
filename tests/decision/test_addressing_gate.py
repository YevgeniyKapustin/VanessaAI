from app.decision.detectors.intent import IntentResult
from app.decision.gate.addressing import is_addressed_to_bot


def test_is_addressed_to_bot_by_mention():
    assert is_addressed_to_bot("hi", mentions_bot=True) is True


def test_is_addressed_to_bot_by_reply():
    assert is_addressed_to_bot("hi", reply_to_bot=True) is True


def test_is_addressed_to_bot_by_name_in_text():
    intent = IntentResult(detected=True, mentions_bot=True)
    assert is_addressed_to_bot("Ванесса, привет", intent=intent) is True


def test_is_not_addressed_to_bot():
    assert is_addressed_to_bot("Личь не делает карты") is False


def test_is_addressed_by_contextual_nickname():
    assert is_addressed_to_bot("продолжай список гомункул") is True
    assert is_addressed_to_bot("гомункул, продолжай список") is True


def test_is_not_addressed_by_status_remark_about_nickname():
    assert is_addressed_to_bot("гомункул работает") is False
    assert is_addressed_to_bot("видите, гомункул работает") is False


def test_is_addressed_by_planner_should_reply():
    assert is_addressed_to_bot(
        "продолжай список гомункул",
        should_reply=True,
    ) is True


def test_reply_to_other_user_blocks_even_when_planner_says_yes():
    assert is_addressed_to_bot(
        "Личь не делает карты",
        reply_to_other_user=True,
        should_reply=True,
    ) is False


def test_is_addressed_in_listen_window_follow_up():
    assert is_addressed_to_bot(
        "продолжай список гомункул",
        in_listen_window=True,
    ) is True
