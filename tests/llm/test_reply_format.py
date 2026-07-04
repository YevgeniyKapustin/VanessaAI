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
