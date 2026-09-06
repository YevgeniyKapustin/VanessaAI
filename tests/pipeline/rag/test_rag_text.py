from vanessa.pipeline.rag.text import truncate_for_embedding


def test_truncate_for_embedding():
    max_chars = 50
    text = "a" * 100
    assert len(truncate_for_embedding(text, max_chars)) == max_chars
    assert truncate_for_embedding("  hello  ", 10) == "hello"
