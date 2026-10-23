import pytest

from services.worker.hermes.file_name import safe_html_name
from services.worker.hermes.html_checks import is_full_document, is_static, unfence
from services.worker.hermes.html_file import FileProblem, split_html_file

PAGE = "<!doctype html><html><body><h1>Отчёт</h1></body></html>"
MAX = 10_000


def tagged(body: str = PAGE, name: str = "bugs-week.html") -> str:
    return f'<vanessa_file name="{name}">\n{body}\n</vanessa_file>'


def test_tagged_file_is_taken_out_and_noted() -> None:
    split = split_html_file(f"До.\n{tagged()}\nГлавное: 3 бага.", max_bytes=MAX)
    assert split.file is not None
    assert split.file.file_name == "bugs-week.html"
    assert split.file.content == PAGE
    assert split.problems == ()
    assert "<html" not in split.text
    assert "[HTML file attached: bugs-week.html, 1 KB]" in split.text
    assert split.text.startswith("До.")
    assert split.text.endswith("Главное: 3 бага.")


def test_plain_answer_is_unchanged() -> None:
    split = split_html_file("VAN-1 в работе", max_bytes=MAX)
    assert split.text == "VAN-1 в работе"
    assert split.file is None
    assert split.problems == ()


def test_fenced_tagged_file_keeps_only_the_note() -> None:
    inner = tagged("```html\n" + PAGE + "\n```")
    answer = "```html\n" + inner + "\n```\nИтог"
    split = split_html_file(answer, max_bytes=MAX)
    assert split.file is not None
    assert split.file.content == PAGE
    assert split.problems == ()
    assert "```" not in split.text


@pytest.mark.parametrize(
    "answer",
    [f"Вот:\n```html\n{PAGE}\n```", f"Вот:\n{PAGE}", f"Вот: <!-- x -->\n{PAGE}"],
)
def test_untagged_page_is_a_file_with_default_name(answer: str) -> None:
    split = split_html_file(answer, max_bytes=MAX)
    assert split.file is not None
    assert split.file.file_name == "report.html"
    assert "<body" not in split.text


@pytest.mark.parametrize(
    ("answer", "problem"),
    [
        (tagged("<p>just a part</p>"), FileProblem.NOT_HTML),
        ("Код:\n```html\n<p>x</p>\n```", FileProblem.NOT_HTML),
        (tagged(PAGE.replace("<h1>", "<script>alert(1)</script><h1>")), FileProblem.ACTIVE),
        (tagged(PAGE.replace("<h1>", '<h1 onclick="x()">')), FileProblem.ACTIVE),
        (tagged("<!doctype html><html>" + "x" * MAX + "</html>"), FileProblem.TOO_BIG),
    ],
)
def test_bad_file_is_refused_and_never_shown(answer: str, problem: FileProblem) -> None:
    split = split_html_file(answer, max_bytes=MAX)
    assert split.file is None
    assert split.problems == (problem,)
    assert "<p>" not in split.text
    assert "<script" not in split.text
    assert "onclick" not in split.text
    assert split.text.startswith("[HTML file not sent") or "Код:" in split.text


@pytest.mark.parametrize(
    "answer",
    [
        'Итог: 2 бага.\n<vanessa_file name="a.html">\n<!doctype html><html><body>',
        "Итог: 2 бага.\n<!doctype html><html><body><table>",
        "Итог: 2 бага.\n```html\n<!doctype html><html><body>",
    ],
)
def test_cut_file_drops_the_rest(answer: str) -> None:
    split = split_html_file(answer, max_bytes=MAX)
    assert split.file is None
    assert FileProblem.CUT in split.problems
    assert split.text == "Итог: 2 бага.\n[HTML file not sent: it was cut off]"


def test_second_file_is_refused() -> None:
    answer = tagged(name="one.html") + "\n" + tagged(name="two.html")
    split = split_html_file(answer, max_bytes=MAX)
    assert split.file is not None
    assert split.file.file_name == "one.html"
    assert split.problems == (FileProblem.EXTRA,)


def test_unquoted_name_attribute() -> None:
    split = split_html_file(f"<vanessa_file name=q3.html>{PAGE}</vanessa_file>", max_bytes=MAX)
    assert split.file is not None
    assert split.file.file_name == "q3.html"


def test_tag_without_name_gets_default() -> None:
    split = split_html_file(f"<vanessa_file>{PAGE}</vanessa_file>", max_bytes=MAX)
    assert split.file is not None
    assert split.file.file_name == "report.html"


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        ("Bugs Week.html", "bugs-week.html"),
        ("../../etc/passwd", "passwd.html"),
        ("C:\\x\\Отчёт по задачам.HTM", "отчёт-по-задачам.html"),
        ("a<b>|c?.html", "a-b-c.html"),
        ("", "report.html"),
        (None, "report.html"),
        ("---.html", "report.html"),
        ("x" * 90, "x" * 60 + ".html"),
    ],
)
def test_safe_html_name(raw: str | None, name: str) -> None:
    assert safe_html_name(raw) == name


def test_checks() -> None:
    assert unfence("```html\n<p>\n```") == "<p>"
    assert unfence(" <p> ") == "<p>"
    assert is_full_document(PAGE)
    assert not is_full_document(PAGE[:-7])
    assert is_static(PAGE)
    assert not is_static('<a href="javascript:x()">')
    assert not is_static('<meta http-equiv="refresh" content="0;url=x">')
    assert not is_static("<form action=x>")
