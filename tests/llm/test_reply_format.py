from app.llm.format.reply_format import capitalize_sentences


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
