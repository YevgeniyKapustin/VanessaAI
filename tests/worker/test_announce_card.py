"""The deploy card: grouping commits by card, and the folded HTML around them."""

from services.worker.announce.card import card_key, card_rows, topic_of, uncarded
from services.worker.announce.card_render import build_card, card_anchor
from services.worker.announce.models import Item

ITEMS = (
    Item(title="[ABC-101] Закрепить выпуск навыков", author="Анна Петрова"),
    Item(title="[ABC-101] Сохранить контракты", author="Анна Петрова"),
    Item(title="Merge branch 'feature/xyz-202-moa' into 'production'", author="Игорь"),
    Item(title="[XYZ-202] Отметки после обрыва", author="Игорь"),
    Item(title="Ссылки на чаты открываются в той же вкладке", author="Мария"),
)
HEADER = 'Релиз <a href="https://git.example/-/pipelines/79545">v0.1.6 (79545)</a>'
BULLETS = ("• Новый чат теперь и в вебе", "• Отметки прочитанного живут")
FOOTER = '<a href="https://grafana.example/d/tenants">Раскатка тенантов на проде</a>'
CARD_URL = "https://board.example/ws/browse/{card}/"


def test_card_key_reads_the_id_from_the_title() -> None:
    assert card_key("[ABC-101] Что-то") == "ABC-101"
    assert card_key("XYZ-202: Зафиксировать событие") == "XYZ-202"
    assert card_key("Merge branch 'feature/xyz-202-prod'") == "XYZ-202"
    assert card_key("Свести production в ветку") == ""


def test_topic_drops_the_card_tag_and_cuts_long_titles() -> None:
    assert topic_of("[ABC-101] Закрепить выпуск навыков") == "Закрепить выпуск навыков"
    assert topic_of("XYZ-202: Описать наблюдаемость") == "Описать наблюдаемость"
    assert topic_of("x" * 80).endswith("…")


def test_rows_group_by_card_and_put_the_biggest_first() -> None:
    rows = card_rows(ITEMS)
    assert [row.card for row in rows] == ["ABC-101", "XYZ-202"]
    assert rows[0].count == 2
    assert rows[0].authors == "Анна Петрова"
    assert rows[0].topic == "Закрепить выпуск навыков"
    # A merge title is never the «о чём» line.
    assert rows[1].topic == "Отметки после обрыва"


def test_rows_keep_at_most_five_cards() -> None:
    items = tuple(
        Item(title=f"[ABC-{100 + index}] Изменение", author="dev") for index in range(9)
    )
    assert len(card_rows(items)) == 5


def test_uncarded_lists_commits_without_a_card() -> None:
    titles = [item.title for item in uncarded(ITEMS)]
    assert titles == ["Ссылки на чаты открываются в той же вкладке"]


def test_card_shows_summary_and_folds_the_rest() -> None:
    html = build_card(
        header_html=HEADER,
        bullets=BULLETS,
        items=ITEMS,
        total=143,
        footer_html=FOOTER,
    )
    visible, folded = html.split("<details>", 1)
    assert HEADER in visible
    assert "Новый чат теперь и в вебе" in visible
    assert "<table>" not in visible
    assert "разбор: 143 коммита, 2 карточки" in folded
    assert "<td>ABC-101</td><td>Анна Петрова · 2</td>" in folded
    assert "без карточки" in folded
    assert FOOTER in folded
    assert "<summary>" in folded


def test_card_escapes_the_commit_text() -> None:
    html = build_card(
        header_html=HEADER,
        bullets=("• <script>alert(1)</script>",),
        items=(Item(title="[ABC-1] <b>не жирный</b>", author="a & b"),),
        total=1,
    )
    assert "<script>" not in html
    assert "&lt;b&gt;" in html
    assert "a &amp; b" in html


def test_without_cards_the_fold_still_explains_the_release() -> None:
    html = build_card(
        header_html=HEADER,
        bullets=(),
        items=(Item(title="Свести production в ветку", author="Игорь"),),
        total=1,
    )
    assert "разбор: 1 коммит, 0 карточек" in html
    assert "<table>" not in html
    assert "Свести production в ветку" in html


def test_without_a_footer_no_empty_paragraph_appears() -> None:
    html = build_card(header_html=HEADER, bullets=(), items=(), total=0)
    assert html.endswith("</details>")
    assert "<p></p>" not in html


def test_every_card_links_to_its_own_card_on_the_board() -> None:
    html = build_card(
        header_html=HEADER,
        bullets=(),
        items=ITEMS,
        total=143,
        card_url=CARD_URL,
    )
    assert '<td><a href="https://board.example/ws/browse/ABC-101/">ABC-101</a></td>' in html
    assert '<td><a href="https://board.example/ws/browse/XYZ-202/">XYZ-202</a></td>' in html
    assert "<td>ABC-101</td>" not in html


def test_without_a_template_card_ids_stay_plain_text() -> None:
    html = build_card(header_html=HEADER, bullets=(), items=ITEMS, total=143)
    assert "<td>ABC-101</td>" in html
    assert '<a href="https://board' not in html


def test_card_anchor_carries_the_id_into_the_template_and_escapes_it() -> None:
    assert card_anchor("", "ABC-101") == "ABC-101"
    assert card_anchor(" ", "ABC-101") == "ABC-101"
    assert (
        card_anchor("https://e/browse/{card}/?a=1&b=2", "ABC-101")
        == '<a href="https://e/browse/ABC-101/?a=1&amp;b=2">ABC-101</a>'
    )
