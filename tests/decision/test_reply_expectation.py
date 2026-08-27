from app.decision.gate.reply_expectation import (
    expects_follow_up_after_bot,
    is_contextual_vocative_address,
    is_conversation_closure,
    is_dismissal_request,
    is_third_party_about_bot,
    is_unsolicited_remark,
    listen_window_warrants_reply,
    mention_warrants_reply,
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


def test_bare_mention_warrants_reply():
    assert mention_warrants_reply("ванесса") is True
    assert mention_warrants_reply("hi") is True


def test_mention_warrants_reply_with_reply_to_bot():
    assert mention_warrants_reply(
        "да именно",
        reply_to_bot=True,
    ) is True


def test_mention_warrants_reply_with_planner_go_ahead():
    assert mention_warrants_reply(
        "ванесса",
        should_reply=True,
    ) is True


def test_status_remark_mention_does_not_warrant_reply():
    assert mention_warrants_reply("ванесса работает") is False
    assert mention_warrants_reply("видите, ванесса работает") is False


def test_closer_mention_does_not_warrant_reply():
    assert mention_warrants_reply("ванесса, пока") is False


def test_listen_window_warrants_reply_question():
    assert listen_window_warrants_reply(
        "а про токены?",
        should_reply=None,
        has_question=True,
        trigger_detected=False,
    ) is True


def test_listen_window_warrants_reply_neutral_substantive():
    # A substantive continuation right after the bot's reply ("ну чет ваще
    # мало") participates in the thread even with a neutral planner.
    assert listen_window_warrants_reply(
        "ну чет ваще мало",
        should_reply=None,
        has_question=False,
        trigger_detected=False,
    ) is True


def test_listen_window_warrants_reply_planner_veto():
    assert listen_window_warrants_reply(
        "ну чет ваще мало",
        should_reply=False,
        has_question=False,
        trigger_detected=False,
    ) is False


def test_listen_window_warrants_reply_planner_affirm():
    assert listen_window_warrants_reply(
        "что-то",
        should_reply=True,
        has_question=False,
        trigger_detected=False,
    ) is True


def test_listen_window_warrants_reply_third_party_stays_silent():
    assert listen_window_warrants_reply(
        "почему она меня игнорирует",
        should_reply=None,
        has_question=True,
        trigger_detected=False,
    ) is False


def test_listen_window_warrants_reply_unsolicited_stays_silent():
    assert listen_window_warrants_reply(
        "гомункул работает",
        should_reply=None,
        has_question=False,
        trigger_detected=False,
    ) is False
