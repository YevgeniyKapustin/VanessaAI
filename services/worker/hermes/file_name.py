"""Safe ``.html`` file names for generated reports."""

from __future__ import annotations

import re

DEFAULT_STEM = "report"
MAX_STEM_CHARS = 60
_EXTENSION_RE = re.compile(r"\.x?html?$", re.IGNORECASE)
_UNSAFE_RE = re.compile(r"[^\w-]+")
_DASHES_RE = re.compile(r"-{2,}")


def safe_html_name(raw: str | None) -> str:
    """Letters, digits, ``_`` and ``-`` only, at most 60 of them, then ``.html``.

    A path keeps only its last part; an empty result becomes ``report.html``.
    """
    name = re.split(r"[\\/]", (raw or "").strip())[-1]
    stem = _EXTENSION_RE.sub("", name.strip())
    stem = _DASHES_RE.sub("-", _UNSAFE_RE.sub("-", stem)).strip("-_").lower()
    stem = stem[:MAX_STEM_CHARS].rstrip("-_")
    return f"{stem or DEFAULT_STEM}.html"
