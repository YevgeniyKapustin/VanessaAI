from app.decision.reply_expectation import (
    expects_follow_up_after_bot,
    is_conversation_closure,
    is_dismissal_request,
    is_unsolicited_remark,
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


def test_dismissal_detects_stop_phrases():
    assert is_dismissal_request("ванесса хватит") is True
    assert is_dismissal_request("перестань отвечать") is True
    assert is_dismissal_request("закрой контекст") is True
    assert is_dismissal_request("хватит") is True


def test_dismissal_allows_normal_messages():
    assert is_dismissal_request("расскажи про меш") is False
    assert is_dismissal_request("хватит ли памяти") is False


def test_unsolicited_remark_detects_group_observations():
    assert is_unsolicited_remark("видите") is True
    assert is_unsolicited_remark("гомункул работает") is True
    assert is_unsolicited_remark("понял") is True


def test_unsolicited_remark_allows_questions_and_follow_ups():
    assert is_unsolicited_remark("а про токены?") is False
    assert is_unsolicited_remark("Гриша меш гексы поле боя") is False


def test_follow_up_requires_substance_after_bot():
    assert expects_follow_up_after_bot(
        "гомункул работает",
        last_prior_role="assistant",
    ) is False
    assert expects_follow_up_after_bot(
        "а про токены?",
        last_prior_role="assistant",
    ) is True
