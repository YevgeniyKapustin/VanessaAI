from app.llm.format.reply_format import capitalize_sentences, strip_trailing_periods


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
