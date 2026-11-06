"""Typographic dashes never reach a chat: see ``vanessa.pipeline.llm.format.dashes``."""

from vanessa.pipeline.llm.format.dashes import plain_dashes


def test_em_dash_becomes_a_hyphen() -> None:
    assert plain_dashes("сделал — проверил") == "сделал - проверил"


def test_every_typographic_dash_variant() -> None:
    assert plain_dashes("a–b‒c―d−e") == "a-b-c-d-e"


def test_plain_hyphen_is_untouched() -> None:
    assert plain_dashes("ABC-6244 и 10-20") == "ABC-6244 и 10-20"


def test_several_dashes_in_one_sentence() -> None:
    text = "он — тот самый — человек, который — да"
    assert plain_dashes(text) == "он - тот самый - человек, который - да"


def test_fenced_code_keeps_its_dashes() -> None:
    text = "было — вот так\n```bash\ncat a | grep —v b\n```\nи всё — готово"
    assert plain_dashes(text) == (
        "было - вот так\n```bash\ncat a | grep —v b\n```\nи всё - готово"
    )


def test_empty_text() -> None:
    assert plain_dashes("") == ""
