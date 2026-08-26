from app.bot.stickers.heuristics import is_sticker_request, reply_tags


def test_reply_tags_greeting():
    assert reply_tags("Ну привет!") == ["greeting"]


def test_reply_tags_delight():
    assert reply_tags("ахах, ну ты даёшь") == ["delight"]


def test_reply_tags_approval_maps_to_love():
    assert reply_tags("Да, точно") == ["love"]


def test_reply_tags_facepalm_maps_to_irritation():
    assert reply_tags("блин, капец") == ["irritation"]


def test_reply_tags_shrug_maps_to_thinking():
    assert reply_tags("хз, не знаю") == ["thinking"]


def test_reply_tags_unknown_returns_empty():
    assert reply_tags("обычное сообщение") == []


def test_reply_tags_none_or_empty():
    assert reply_tags(None) == []
    assert reply_tags("") == []


def test_is_sticker_request_matches_russian_phrases():
    for text in (
        "ванесса кинь стикер",
        "кинь стикер",
        "скинь стикер плиз",
        "дай мне стикер",
        "сбрось стикер",
        "пришли наклейку",
        "покажи стик",
        "ванесса, стикер кинь",
        "кидай стикер",
        "дропни стикер",
    ):
        assert is_sticker_request(text), text


def test_is_sticker_request_matches_english():
    assert is_sticker_request("send me a sticker")
    assert is_sticker_request("send a sticker please")


def test_is_sticker_request_rejects_normal_messages():
    for text in (
        "как дела",
        "стикерпак у тебя классный был",
        "я люблю стикеры",
        "это не стикер",
        "расскажи про стикеры",
        None,
        "",
    ):
        assert not is_sticker_request(text), text


def test_is_sticker_request_case_insensitive():
    assert is_sticker_request("КИНЬ СТИКЕР")
