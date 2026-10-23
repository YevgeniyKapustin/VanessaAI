"""Take a generated HTML file out of a Hermes answer.

Hermes returns a report inline::

    <vanessa_file name="slug.html">
    <!doctype html>…</html>
    </vanessa_file>

The worker sends the file as a Telegram document; the follow-up LLM and
the chat never see the HTML. A short note takes its place in the answer.
A fenced ```html block or a bare document counts as a file too. An HTML
start with no end is a cut file: the rest of the answer is dropped, so a
half page never reaches the chat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from services.worker.hermes.file_name import safe_html_name
from services.worker.hermes.html_checks import is_full_document, is_static, unfence

_FLAGS = re.IGNORECASE | re.DOTALL
_TAGGED_RE = re.compile(r"<vanessa_file\b([^>]*)>(.*?)</vanessa_file\s*>", _FLAGS)
_FENCED_RE = re.compile(r"```[ \t]*html?\b[^\n]*\n(.*?)```", _FLAGS)
_BARE_RE = re.compile(r"(?:<!doctype\s+html\b|<html\b).*?</html\s*>", _FLAGS)
# Left after the whole blocks are gone: a file without its end.
_OPEN_RE = re.compile(
    r"</?vanessa_file\b|```[ \t]*html?\b|<!doctype\s+html\b|<html\b", re.IGNORECASE
)
_NAME_RE = re.compile(
    r"""name\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.IGNORECASE
)
_KB = 1024


class FileProblem(StrEnum):
    TOO_BIG = "too_big"
    CUT = "cut"
    NOT_HTML = "not_html"
    ACTIVE = "active"
    EXTRA = "extra"


# Notes for the follow-up LLM (inside the <hermes_answer> data block).
_NOTES = {
    FileProblem.TOO_BIG: "[HTML file not sent: too big]",
    FileProblem.CUT: "[HTML file not sent: it was cut off]",
    FileProblem.NOT_HTML: "[HTML file not sent: not a whole HTML page]",
    FileProblem.ACTIVE: "[HTML file not sent: it has scripts or forms]",
    FileProblem.EXTRA: "[HTML file not sent: one file per message]",
}


@dataclass(frozen=True, slots=True)
class HtmlFile:
    file_name: str
    content: str

    @property
    def size_bytes(self) -> int:
        return len(self.content.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class SplitAnswer:
    """The answer text without HTML, the file to send, and what was refused."""

    text: str
    file: HtmlFile | None = None
    problems: tuple[FileProblem, ...] = ()


class _Collector:
    """Keeps the first good file and the problems of the others."""

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self.file: HtmlFile | None = None
        self.problems: list[FileProblem] = []

    def take(self, raw_name: str | None, body: str) -> str:
        content = unfence(body)
        problem = self._problem(content)
        if problem is not None:
            return self.refuse(problem)
        self.file = HtmlFile(safe_html_name(raw_name), content)
        size_kb = max(1, round(self.file.size_bytes / _KB))
        return f"[HTML file attached: {self.file.file_name}, {size_kb} KB]"

    def _problem(self, content: str) -> FileProblem | None:
        """The first failed check, in order; None for a good file."""
        checks = (
            (FileProblem.NOT_HTML, lambda: not is_full_document(content)),
            (FileProblem.ACTIVE, lambda: not is_static(content)),
            (FileProblem.EXTRA, lambda: self.file is not None),
            (FileProblem.TOO_BIG, lambda: len(content.encode("utf-8")) > self._max_bytes),
        )
        return next((problem for problem, failed in checks if failed()), None)

    def refuse(self, problem: FileProblem) -> str:
        self.problems.append(problem)
        return _NOTES[problem]


def _name(attributes: str) -> str | None:
    match = _NAME_RE.search(attributes)
    if match is None:
        return None
    return next((group for group in match.groups() if group is not None), None)


def split_html_file(answer: str, *, max_bytes: int) -> SplitAnswer:
    """Split ``answer`` into chat-safe text and at most one HTML file."""
    found = _Collector(max_bytes)
    text = _TAGGED_RE.sub(lambda m: found.take(_name(m.group(1)), m.group(2)), answer)
    # A fence around a tagged file now holds only its note: keep the note.
    text = _FENCED_RE.sub(
        lambda m: found.take(None, m.group(1)) if "<" in m.group(1) else m.group(1),
        text,
    )
    text = _BARE_RE.sub(lambda m: found.take(None, m.group(0)), text)
    cut = _OPEN_RE.search(text)
    if cut is not None:
        text = text[: cut.start()] + found.refuse(FileProblem.CUT)
    return SplitAnswer(
        text=text.strip(), file=found.file, problems=tuple(found.problems)
    )
