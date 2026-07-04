from app.rag.text import truncate_for_embedding


def test_truncate_for_embedding():
    text = "a" * 100
    assert len(truncate_for_embedding(text, 50)) == 50
    assert truncate_for_embedding("  hello  ", 10) == "hello"
