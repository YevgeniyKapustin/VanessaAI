from vanessa.llm.format.message_blocks import split_reply_into_blocks, strip_block_markers


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


def test_fallback_splits_reply_into_short_messages_without_newlines():
    # A normal multi-sentence reply with no `[next]` markers used to arrive as
    # ONE message with line breaks. It must now arrive as several short
    # messages ("1-2 sentences per message"), never a multi-line wall of text.
    reply = (
        "First thought about the garages. "
        "Second thought keeps it going. "
        "Third thought wraps it up."
    )
    blocks = split_reply_into_blocks(reply)
    assert len(blocks) == 2
    assert all("\n" not in block for block in blocks)
    assert "First thought about the garages. Second thought keeps it going." in blocks


def test_fallback_groups_at_most_two_sentences_per_message():
    reply = "One. Two. Three. Four."
    blocks = split_reply_into_blocks(reply)
    assert len(blocks) == 2
    assert blocks == ["One. Two.", "Three. Four."]


def test_fallback_never_joins_paragraphs_with_newline():
    # Paragraphs become separate short messages too, instead of being packed
    # into one message with blank-line breaks.
    reply = "One thought.\n\nAnother thought.\n\nA third one."
    blocks = split_reply_into_blocks(reply)
    assert len(blocks) == 2
    assert all("\n" not in block for block in blocks)


def test_split_does_not_leak_trailing_marker():
    # The model hits the output cap right after emitting `[next]`, so the reply
    # ends with a dangling marker. The fallback splitter must strip it instead of
    # delivering the control tag (or a block containing it) to the chat.
    reply = "First reply text\n[next]"
    blocks = split_reply_into_blocks(reply)
    assert blocks == ["First reply text"]
    assert all("[next]" not in block for block in blocks)


def test_split_only_marker_returns_empty():
    # The whole (truncated) output was just the `[next]` marker — nothing is
    # delivered rather than sending a literal `[next]` message.
    assert split_reply_into_blocks("[next]") == []
    assert split_reply_into_blocks("  [ Next ]  ") == []


def test_split_trailing_marker_custom_marker_is_stripped():
    reply = "A\n<|msg|>"
    blocks = split_reply_into_blocks(reply, marker="<|msg|>")
    assert blocks == ["A"]


def test_split_does_not_leak_marker_inside_content():
    # A marker line in the MIDDLE still splits into blocks, and neither delivered
    # block may contain the marker.
    reply = "Один\n[next]\nДва"
    blocks = split_reply_into_blocks(reply)
    assert blocks == ["Один", "Два"]
    assert all("[next]" not in block for block in blocks)


def test_split_does_not_leak_truncated_marker():
    # The output cap cut the model mid-marker: a dangling `[next` with no closing
    # bracket must not reach a delivered block (the marker regex never matches an
    # unclosed tail, so the sanitizer has to drop it).
    reply = "Первый блок\n[next]\nВторой блок обрезан\n[next"
    blocks = split_reply_into_blocks(reply)
    assert blocks == ["Первый блок", "Второй блок обрезан"]
    assert all("[" not in block for block in blocks)


def test_split_does_not_leak_inline_marker():
    # The model put `[next]` on a content line instead of its own line — strip it
    # from the delivered text, never send the control tag as a chat message.
    reply = "Первый блок [next] Второй блок"
    blocks = split_reply_into_blocks(reply)
    assert blocks == ["Первый блок Второй блок"]
    assert all("[next]" not in block for block in blocks)


def test_strip_block_markers_removes_inline_and_truncated():
    reply = "А [next] Б\n[next\nВ"
    assert strip_block_markers(reply) == "А Б\nВ"


def test_strip_block_markers_truncated_keeps_code_fences():
    # A truncated `[next` inside a fenced code block is content, not a marker —
    # it must survive, only the prose-level marker is removed.
    reply = "текст [next\n```\n[next\n```\nконец"
    assert strip_block_markers(reply) == "текст\n```\n[next\n```\nконец"
