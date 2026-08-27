from app.llm.format.reply_format import (
    capitalize_sentences,
    strip_leading_address,
    strip_trailing_periods,
)


def test_capitalize_sentences_starts_with_upper():
    assert capitalize_sentences("ну ладно поработаю") == "Ну ладно поработаю"


def test_capitalize_sentences_after_punctuation():
    assert capitalize_sentences("да. потом расскажу") == "Да. Потом расскажу"


def test_capitalize_sentences_keeps_short_interjections():
    assert capitalize_sentences("хз") == "хз"
    assert capitalize_sentences("ок") == "ок"


def test_capitalize_sentences_preserves_already_capitalized():
    assert capitalize_sentences("Да, поняла") == "Да, поняла"


def test_fix_lich_spelling_adds_soft_sign():
    assert capitalize_sentences("Лич не делает карты") == "Личь не делает карты"
    assert capitalize_sentences("ну лич работа") == "Ну личь работа"


def test_fix_lich_spelling_keeps_correct_and_other_words():
    assert capitalize_sentences("Личь уже тут") == "Личь уже тут"
    assert capitalize_sentences("личный состав") == "Личный состав"


def test_strip_trailing_period_removes_final_period():
    assert strip_trailing_periods("Понял.") == "Понял"
    assert strip_trailing_periods("Ну да, попал в десятку.") == "Ну да, попал в десятку"
    assert strip_trailing_periods("конец. ") == "конец"


def test_strip_trailing_periods_preserves_ellipsis():
    assert strip_trailing_periods("ну такое...") == "ну такое..."
    assert strip_trailing_periods("...") == "..."


def test_strip_trailing_periods_preserves_internal_periods():
    assert strip_trailing_periods("Да. Потом расскажу.") == "Да. Потом расскажу"


def test_strip_trailing_periods_preserves_question_and_exclamation():
    assert strip_trailing_periods("Что?") == "Что?"
    assert strip_trailing_periods("Красава!") == "Красава!"


def test_strip_trailing_periods_ignores_code_block():
    text = "вот код:\n```python\nx = 1.\n```"
    assert strip_trailing_periods(text) == text


def test_postprocess_strips_period_then_capitalizes():
    text = "ну ладно поработаю."
    assert capitalize_sentences(strip_trailing_periods(text)) == "Ну ладно поработаю"


def test_strip_leading_address_removes_name_prefix():
    assert strip_leading_address("Евгений, привет", "Евгений") == "привет"
    assert strip_leading_address("Евгений: привет", "Евгений") == "привет"
    assert strip_leading_address("евгений, привет", "Евгений") == "привет"


def test_strip_leading_address_handles_guillemets():
    assert strip_leading_address("«Евгений, привет", "Евгений") == "привет"
    assert strip_leading_address("„Евгений, привет", "Евгений") == "привет"


def test_strip_leading_address_uses_nickname_from_parenthesized_name():
    assert (
        strip_leading_address("Капуста, ты гений", "Евгений (Капуста)") == "ты гений"
    )


def test_strip_leading_address_tries_all_name_tokens():
    # The second token ("Капуста") matches even though the first ("Евгений") doesn't.
    assert strip_leading_address("Капуста, смотри", "Евгений Капуста") == "смотри"


def test_strip_leading_address_keeps_name_as_sentence_subject():
    # No address separator — the name is the subject, not an address.
    assert (
        strip_leading_address("Евгений знает ответ", "Евгений") == "Евгений знает ответ"
    )


def test_strip_leading_address_keeps_mid_sentence_mention():
    assert (
        strip_leading_address("Ну, Евгений сам сказал", "Евгений")
        == "Ну, Евгений сам сказал"
    )


def test_strip_leading_address_keeps_reply_when_no_name_provided():
    assert strip_leading_address("Евгений, привет", None) == "Евгений, привет"
    assert strip_leading_address("привет", "Евгений") == "привет"


def test_strip_leading_address_never_returns_empty():
    assert strip_leading_address("Евгений,", "Евгений") == "Евгений,"


def test_strip_leading_address_before_capitalize_keeps_casing():
    # Integration-style: matches the provider pipeline order (strip then capitalize).
    text = strip_leading_address("Евгений, привет мир", "Евгений")
    assert capitalize_sentences(strip_trailing_periods(text)) == "Привет мир"
