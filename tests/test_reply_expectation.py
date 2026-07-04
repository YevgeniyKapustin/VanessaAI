from app.decision.reply_expectation import (
    expects_follow_up_after_bot,
    is_conversation_closure,
)


def test_closure_detects_departure_message():
    assert is_conversation_closure("ну ладно надо будет поработать пойти") is True


def test_closure_detects_goodbye():
    assert is_conversation_closure("ладно, пока") is True


def test_closure_allows_follow_up():
    assert is_conversation_closure("про токены тоже интересно") is False


def test_follow_up_requires_bot_was_last_speaker():
    assert expects_follow_up_after_bot(
        "про токены тоже интересно",
        last_prior_role="assistant",
    ) is True
    assert expects_follow_up_after_bot(
        "про токены тоже интересно",
        last_prior_role="user",
    ) is False
    assert expects_follow_up_after_bot(
        "ну ладно пойду",
        last_prior_role="assistant",
    ) is False
