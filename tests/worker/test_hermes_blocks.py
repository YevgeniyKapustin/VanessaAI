"""The follow-up split into short messages, and the report stylesheet."""

from services.worker.hermes.blocks import MAX_BLOCKS, followup_blocks
from services.worker.hermes.compose import final_text
from services.worker.hermes.html_file import HtmlFile
from services.worker.hermes.report_style import styled_file, with_report_style
from vanessa.config.content_hermes import get_report_css
from vanessa.contracts.outbound import MESSAGE_MAX_CHARS

CSS = ".sheet{color:red}"
STYLE = f"<style>\n{CSS}\n</style>"


def test_next_markers_split_and_drop_trailing_periods() -> None:
    text = "Глянула.\n[next]\nДве задачи горят.\n[next]\n\n[next]\nОдна ждёт тебя"
    assert followup_blocks(text, marker="[next]") == [
        "Глянула",
        "Две задачи горят",
        "Одна ждёт тебя",
    ]


def test_empty_text_has_no_blocks() -> None:
    assert followup_blocks("  ") == []


def test_too_many_blocks_are_cut_with_ellipsis() -> None:
    text = "\n[next]\n".join(f"блок {index}" for index in range(MAX_BLOCKS + 3))
    blocks = followup_blocks(text, marker="[next]")
    assert len(blocks) == MAX_BLOCKS
    assert blocks[-1] == f"блок {MAX_BLOCKS - 1}…"


def test_a_word_longer_than_a_message_is_cut() -> None:
    blocks = followup_blocks("z" * (MESSAGE_MAX_CHARS * 2 + 5))
    assert [len(block) for block in blocks] == [MESSAGE_MAX_CHARS] * 2 + [5]


def test_final_text_keeps_blocks_only_when_asked() -> None:
    raw = "думаю\n[answer]\nраз\n[next]\nдва [forward]"
    assert final_text(raw) == "раз\nдва"
    assert final_text(raw, keep_blocks=True) == "раз\n[next]\nдва"
    assert final_text("[answer]\n[next]\n", keep_blocks=True) == ""
    assert final_text("[answer]\n[ignore]", keep_blocks=True) == ""


def test_style_goes_right_after_head() -> None:
    page = '<!doctype html><html lang="ru"><head><title>t</title></head></html>'
    styled = with_report_style(page, CSS)
    assert styled == page.replace("<head>", "<head>" + STYLE)


def test_style_without_head_goes_after_html_or_first() -> None:
    page = "<html><header>x</header></html>"
    assert with_report_style(page, CSS) == "<html>" + STYLE + page[len("<html>") :]
    assert with_report_style("<p>x</p>", CSS) == STYLE + "<p>x</p>"
    assert with_report_style(page, "  ") == page


def test_styled_file_keeps_name_and_none() -> None:
    assert styled_file(None, CSS) is None
    file = styled_file(HtmlFile("a.html", "<html></html>"), CSS)
    assert file == HtmlFile("a.html", "<html>" + STYLE + "</html>")


def test_report_css_is_the_static_sheet() -> None:
    css = get_report_css()
    assert ".panels" in css
    assert ".stamp" in css
    assert "prefers-color-scheme: dark" in css
    for active in ("<", "url(", "@import", "expression("):
        assert active not in css
