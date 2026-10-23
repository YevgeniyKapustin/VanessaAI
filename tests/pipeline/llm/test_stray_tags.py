from vanessa.pipeline.llm.format.stray_tags import strip_stray_tags


def test_drops_invented_tag_at_line_end():
    text = "Ща гляну, отвечу отдельно. [forward]\nА пока вот что"

    assert strip_stray_tags(text) == "Ща гляну, отвечу отдельно.\nА пока вот что"


def test_drops_invented_tag_alone_on_line():
    assert strip_stray_tags("раз\n[end]\nдва") == "раз\n\nдва"


def test_keeps_known_markers_args_and_inline_text():
    text = "раз\n[next]\nдва [ignore]\n[photo:1]\nнажми [ok] и всё\n[Привет]"

    assert strip_stray_tags(text) == text


def test_keeps_custom_marker_and_code():
    text = "раз [split]\n```\nx = [done]\n```"

    assert strip_stray_tags(text, keep=("[split]",)) == text
