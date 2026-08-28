from app.llm.format.answer_tag import (
    extract_answer,
    extract_ignore_reason,
    has_ignore_marker,
)


def test_extract_answer_splits_reasoning_and_reply():
    raw = (
        "Тут стоит ответить про крабера, потому что он упомянут в контексте.\n"
        "Надо коротко и по делу.\n\n"
        "[answer]\n"
        "Крабер — местный, у него своя пещера."
    )
    reply, reasoning = extract_answer(raw)
    assert reply == "Крабер — местный, у него своя пещера."
    assert "крабера" in reasoning
    assert "Крабер" not in reasoning


def test_extract_answer_falls_back_to_full_output_without_tag():
    raw = "Просто ответ без рассуждений"
    reply, reasoning = extract_answer(raw)
    assert reply == "Просто ответ без рассуждений"
    assert reasoning == ""


def test_extract_answer_uses_last_tag_when_repeated():
    raw = (
        "черновик 1\n[answer]\nпервый ответ\n"
        "ещё подумала\n[answer]\nитоговый ответ"
    )
    reply, reasoning = extract_answer(raw)
    assert reply == "итоговый ответ"
    assert "черновик 1" in reasoning
    assert "ещё подумала" in reasoning


def test_extract_answer_case_insensitive_tag():
    raw = "подумала\n[ANSWER]\nответ"
    reply, reasoning = extract_answer(raw)
    assert reply == "ответ"
    assert reasoning == "подумала"


def test_extract_answer_tag_with_spaces():
    raw = "подумала\n[ Answer ]\nответ"
    reply, _ = extract_answer(raw)
    assert reply == "ответ"


def test_extract_answer_ignores_tag_inside_code_block():
    raw = (
        "Нужен код.\n```\n[answer]\nэто код, не ответ\n```\n"
        "[answer]\nВот код ниже."
    )
    reply, reasoning = extract_answer(raw)
    assert reply == "Вот код ниже."
    # The code-block tag must not split: the real final tag after the fence wins.
    assert "[answer]" in reasoning


def test_extract_answer_empty_input():
    reply, reasoning = extract_answer("")
    assert reply == ""
    assert reasoning == ""


def test_extract_answer_whitespace_only():
    reply, reasoning = extract_answer("   \n  ")
    assert reply == ""
    assert reasoning == ""


def test_has_ignore_marker_true_for_lone_tag():
    assert has_ignore_marker("[ignore]") is True


def test_has_ignore_marker_true_after_answer_tag():
    # The model emits [answer] then ONLY the ignore marker (no message).
    assert has_ignore_marker("[answer]\n[ignore]") is True


def test_has_ignore_marker_true_when_answer_tag_missing():
    # No [answer] tag → the whole output (reasoning + marker) lands in the reply;
    # the lone marker line is still a refusal signal.
    assert has_ignore_marker("это повтор, молчу\n[ignore]") is True


def test_has_ignore_marker_true_case_insensitive_and_spaces():
    assert has_ignore_marker("[IGNORE]") is True
    assert has_ignore_marker("[ ignore ]") is True


def test_has_ignore_marker_true_with_reason_after_tag():
    # The model appends a short internal reason after the tag for debugging; the
    # line still starts with the marker, so it remains a refusal signal.
    assert has_ignore_marker("[ignore] повтор того же вопроса") is True
    assert has_ignore_marker("[ignore] пустой филлер") is True


def test_has_ignore_marker_true_with_reason_after_tag_in_multiline():
    assert has_ignore_marker("это повтор\n[ignore] тот же вопрос") is True


def test_has_ignore_marker_false_when_embedded_in_sentence():
    # A marker inside a sentence is a normal reply, not a refusal.
    assert has_ignore_marker("он написал [ignore] в чате") is False
    # A marker in the middle of a line (not at its start) is also not a refusal.
    assert has_ignore_marker("это [ignore] повторил я") is False


def test_has_ignore_marker_false_for_normal_reply_and_empty():
    assert has_ignore_marker("Крабер — местный, у него своя пещера.") is False
    assert has_ignore_marker("") is False
    assert has_ignore_marker(None) is False


def test_extract_ignore_reason_returns_text_after_tag():
    assert extract_ignore_reason("[ignore] повтор того же вопроса") == "повтор того же вопроса"
    assert extract_ignore_reason("[ignore]пустой филлер") == "пустой филлер"


def test_extract_ignore_reason_empty_without_reason():
    assert extract_ignore_reason("[ignore]") == ""
    assert extract_ignore_reason("[IGNORE]") == ""


def test_extract_ignore_reason_empty_without_marker():
    assert extract_ignore_reason("Крабер — местный, у него своя пещера.") == ""
    assert extract_ignore_reason("он написал [ignore] в чате") == ""
    assert extract_ignore_reason("") == ""
    assert extract_ignore_reason(None) == ""
