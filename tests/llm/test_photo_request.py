from app.llm.photo_request import is_photo_request


def test_is_photo_request_matches_russian_phrases():
    for text in (
        "отправь фото",
        "кинь картинку",
        "скинь фотку",
        "сбрось скрин",
        "дай пикчу",
        "покажи скриншот",
        "верни то фото",
        "пришли мне картинку",
        "покажи фото кота",
        "кинь плиз картинку",
        "скинь пожалуйста фотку",
    ):
        assert is_photo_request(text), text


def test_is_photo_request_matches_any_variants():
    """The reported scenario: «просил любую отправить» / «отправь любую»."""
    for text in (
        "отправь любую картинку",
        "пришли какую-нибудь картинку",
        "кинь какую угодно фото",
        "скинь любую фотку",
        "пришли любую",
    ):
        assert is_photo_request(text), text


def test_is_photo_request_matches_plural_forms():
    for text in (
        "отправьте фото",
        "скиньте картинку",
        "покажите скрин",
        "пришлите фотку",
        "дайте пикчу",
    ):
        assert is_photo_request(text), text


def test_is_photo_request_matches_noun_verb_order():
    for text in (
        "фото кинь",
        "картинку отправь",
        "скрин покажи",
        "фотку скинь",
    ):
        assert is_photo_request(text), text


def test_is_photo_request_matches_english():
    assert is_photo_request("send me a photo")
    assert is_photo_request("send a picture please")
    assert is_photo_request("show me an image")
    assert is_photo_request("return the photo")


def test_is_photo_request_rejects_normal_messages():
    for text in (
        "привет как дела",
        "что делаешь",
        "какая картинка красивая",
        "у меня есть фото в телефоне",
        "я отправлю фото позже",
        "сфоткай меня",
        "как сделать в фотошопе",
        "отправь мне стикер",
        "отправь файл",
        "покажи как это работает",
        "отправь любую работу",
    ):
        assert not is_photo_request(text), text


def test_is_photo_request_empty():
    assert not is_photo_request("")
    assert not is_photo_request(None)


def test_is_photo_request_case_insensitive():
    assert is_photo_request("КИНЬ КАРТИНКУ")
    assert is_photo_request("SEND ME A PHOTO")
