from app.llm.format.answer_tag import extract_answer


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
