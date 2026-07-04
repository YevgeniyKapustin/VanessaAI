from app.decision.gate.reply_expectation import (
    expects_follow_up_after_bot,
    is_contextual_vocative_address,
    is_conversation_closure,
    is_dismissal_request,
    is_third_party_about_bot,
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
    assert is_dismissal_request("да всё сгинь") is True
    assert is_dismissal_request("уйди, закрой сессию") is True


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


def test_third_party_about_bot_detects_gossip():
    assert is_third_party_about_bot("почему она меня игнорирует") is True
    assert is_third_party_about_bot("она опять молчит") is True
    assert is_third_party_about_bot(
        "она вот плохо понимает когда ты начинаешь монолог вести"
    ) is True
    assert is_third_party_about_bot(
        "ну я хз она типо думает ей ли отвечают"
    ) is True


def test_third_party_about_bot_allows_direct_address():
    assert is_third_party_about_bot("ванесса, почему ты меня игнорируешь") is False
    assert is_third_party_about_bot("почему ты меня игнорируешь") is False


def test_contextual_vocative_address_detects_nickname_imperative():
    assert is_contextual_vocative_address("продолжай список гомункул") is True
    assert is_contextual_vocative_address("гомункул, продолжай список") is True
    assert is_contextual_vocative_address("напиши ещё пункты") is True


def test_contextual_vocative_address_rejects_status_remarks():
    assert is_contextual_vocative_address("гомункул работает") is False
    assert is_contextual_vocative_address("видите, гомункул работает") is False
