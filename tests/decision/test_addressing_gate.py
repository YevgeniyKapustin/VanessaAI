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
