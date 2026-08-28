from app.llm.format.message_blocks import split_reply_into_blocks, strip_block_markers


def test_strip_block_markers_removes_marker_lines():
    reply = "Первый блок\n[next]\nВторой блок"
    assert strip_block_markers(reply) == "Первый блок\nВторой блок"


def test_strip_block_markers_case_insensitive_and_spaces():
    reply = "А\n  [ Next ]  \nБ"
    assert strip_block_markers(reply) == "А\nБ"


def test_strip_block_markers_keeps_code_fences():
    reply = "текст\n```\n[next]\n```\nконец"
    assert strip_block_markers(reply) == "текст\n```\n[next]\n```\nконец"


def test_split_marks_into_blocks():
    reply = "Один\n[next]\nДва\n[next]\nТри"
    assert split_reply_into_blocks(reply) == ["Один", "Два", "Три"]


def test_split_single_reply_no_marker():
    assert split_reply_into_blocks("Просто ответ") == ["Просто ответ"]


def test_split_marker_inside_code_is_not_separator():
    reply = "Начало\n```\n[next]\n```\nПродолжение"
    blocks = split_reply_into_blocks(reply)
    assert len(blocks) == 1
    assert "[next]" in blocks[0]


def test_split_fallback_on_long_reply_without_markers():
    # Three sentences, tiny target -> deterministic sentence-aware split.
    reply = (
        "Первое предложение довольно длинное. "
        "Второе предложение тоже длинное. "
        "Третье предложение ещё одно."
    )
    blocks = split_reply_into_blocks(reply, fallback_target_chars=20)
    assert len(blocks) >= 2
    assert all(block.strip() for block in blocks)


def test_split_hard_cap_every_block_under_max():
    reply = "слово " * 5000
    blocks = split_reply_into_blocks(reply, max_chars=1000)
    assert len(blocks) > 1
    assert all(len(block) <= 1000 for block in blocks)


def test_split_empty_reply_returns_empty():
    assert split_reply_into_blocks("") == []
    assert split_reply_into_blocks("   ") == []


def test_split_custom_marker():
    reply = "A\n<|msg|>\nB"
    assert split_reply_into_blocks(reply, marker="<|msg|>") == ["A", "B"]


def test_split_ignores_differently_spelled_tag_with_custom_marker():
    # With a custom marker, the default `[next]` spelling is not a separator.
    reply = "A\n[next]\nB"
    assert split_reply_into_blocks(reply, marker="<|msg|>") == ["A\n[next]\nB"]


def test_split_fallback_splits_chat_text_without_punctuation():
    # Casual chat often has no sentence punctuation — the fallback must still
    # split a long reply into short blocks instead of one wall of text.
    reply = "первое сообщение про крабера и его гаражи " * 3
    blocks = split_reply_into_blocks(reply, fallback_target_chars=40)
    assert len(blocks) > 1
    assert all(len(block) <= 40 for block in blocks)


def test_split_fallback_splits_long_single_paragraph():
    # One long unpunctuated paragraph (typical model output) → several blocks,
    # each at most the target size.
    reply = " ".join(f"слово{i}" for i in range(200))
    blocks = split_reply_into_blocks(reply, fallback_target_chars=120)
    assert len(blocks) > 1
    assert all(len(block) <= 120 for block in blocks)
