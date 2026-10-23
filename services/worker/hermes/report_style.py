"""Add the report stylesheet to a generated HTML page.

Hermes writes the markup only (the sheet classes from ``run_instructions``);
the worker adds the shared stylesheet, so every report has the same look.
The sheet goes first in the page, so the page's own CSS can override it.
It is added after the file checks: it is our CSS, not Hermes' content.
"""

from __future__ import annotations

import re
from dataclasses import replace

from services.worker.hermes.html_file import HtmlFile

_HEAD_RE = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
_HTML_RE = re.compile(r"<html\b[^>]*>", re.IGNORECASE)


def with_report_style(content: str, css: str) -> str:
    """``content`` with ``<style>css</style>`` right after ``<head>``.

    No ``<head>``: right after ``<html>``; no ``<html>``: at the start.
    An empty ``css`` keeps the page as is.
    """
    if not css.strip():
        return content
    style = f"<style>\n{css.strip()}\n</style>"
    for pattern in (_HEAD_RE, _HTML_RE):
        match = pattern.search(content)
        if match is not None:
            return content[: match.end()] + style + content[match.end() :]
    return style + content


def styled_file(file: HtmlFile | None, css: str) -> HtmlFile | None:
    """The file with the report stylesheet added; None stays None."""
    if file is None:
        return None
    return replace(file, content=with_report_style(file.content, css))
