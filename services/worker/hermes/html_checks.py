"""Checks for a generated HTML file before the chat gets it.

A file is sent only when it is one whole document (``<!doctype html>`` or
``<html>`` … ``</html>``) and static: anyone in the chat can steer Hermes,
so scripts, frames, forms, event handlers and redirects are refused.
"""

from __future__ import annotations

import re

_DOCUMENT_RE = re.compile(
    r"^(?:<!--.*?-->\s*)*(?:<!doctype\s+html\b|<html\b).*</html\s*>$",
    re.IGNORECASE | re.DOTALL,
)
_ACTIVE_RE = re.compile(
    r"<\s*(?:script|iframe|frame|object|embed|form|base)\b"
    r"|<[^>]*\son[a-z]+\s*="
    r"|javascript\s*:"
    r"|http-equiv\s*=\s*[\"']?refresh",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)\n?```$", re.DOTALL)


def unfence(body: str) -> str:
    """The body without one wrapping Markdown code fence, stripped."""
    body = body.strip()
    match = _FENCE_RE.match(body)
    return match.group(1).strip() if match else body


def is_full_document(content: str) -> bool:
    """True for one whole HTML document; a cut one has no ``</html>``."""
    return bool(_DOCUMENT_RE.match(content))


def is_static(content: str) -> bool:
    """True when the page runs no code and sends nothing anywhere."""
    return _ACTIVE_RE.search(content) is None
