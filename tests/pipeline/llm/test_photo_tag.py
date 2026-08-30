from vanessa.pipeline.llm.format.photo_tag import extract_photo_index


def test_extract_photo_index_strips_marker():
    reply = "Держи\n[photo:1]"
    clean, index = extract_photo_index(reply)
    assert index == 1
    assert clean == "Держи"


def test_extract_photo_index_without_marker():
    clean, index = extract_photo_index("обычный ответ")
    assert index is None
    assert clean == "обычный ответ"


def test_extract_photo_index_leaves_marker_inside_code():
    reply = "```\n[photo:2]\n```\nок"
    clean, index = extract_photo_index(reply)
    assert index is None
    assert "[photo:2]" in clean


def test_extract_photo_index_takes_first_marker():
    reply = "один\n[photo:1]\n[photo:3]"
    clean, index = extract_photo_index(reply)
    assert index == 1
    assert "[photo:3]" not in clean


def test_extract_photo_index_empty():
    clean, index = extract_photo_index("")
    assert index is None
    assert clean == ""
