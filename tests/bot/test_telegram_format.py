from app.bot.telegram_format import markdown_to_telegram_html
from app.llm.format.reply_format import capitalize_sentences


def test_markdown_fenced_code_block():
    text = "Вот пример:\n```python\ndef mesh():\n    return 1\n```"
    html = markdown_to_telegram_html(text)

    assert "<pre><code>def mesh():\n    return 1</code></pre>" in html
    assert "Вот пример:" in html
    assert "```" not in html


def test_markdown_inline_code():
    html = markdown_to_telegram_html("Вызови `generate_mesh()` и всё")

    assert "Вызови <code>generate_mesh()</code> и всё" == html


def test_markdown_escapes_html_in_prose():
    html = markdown_to_telegram_html("a < b && c > d")

    assert html == "a &lt; b &amp;&amp; c &gt; d"


def test_capitalize_skips_fenced_code():
    text = "вот код:\n```python\nx = 1. y = 2\n```"
    result = capitalize_sentences(text)

    assert result.startswith("Вот код:")
    assert "y = 2" in result
    assert "Y = 2" not in result
