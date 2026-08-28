"""Deterministic reply-length detector.

Zero-cost complement to the planner's ``detail`` field: catches explicit
"give me more" / "keep it short" phrasing in the raw message so a follow-up like
«давай подробнее» right after a too-short answer is honored without an extra
LLM call. Explicit phrasing overrides the planner's judgment — the user said
what they want.

Only *unambiguous* phrasing is matched here. Ambiguous filler that often means
something else (e.g. «короче» as the discourse marker "anyway", «развернуть» as
"deploy/rotate") is deliberately left to the planner LLM, which can read the
intent from context.
"""

from __future__ import annotations

import re

# Explicit "give me more detail" phrases. Matched as substrings (case-insensitive)
# so «давай подробнее», «расскажи подробно», «поподробнее», «в деталях»,
# «развёрнуто» all count.
_MORE_DETAIL_PATTERNS = (
    r"подробн\w*",        # подробно, подробнее, подробный, подробней
    r"поподробнее",        # по-подробнее
    r"поподробней",
    r"в деталях",
    r"детальнее",
    r"разверни ответ",
    r"развёрнут\w*",       # развёрнуто, развёрнутый (ё)
    r"развернуто",         # без ё: развернуто, развернутое, развернутый
)

# Explicit "keep it short" phrases. Each one is a clear instruction, not a
# discourse filler.
_BRIEF_PATTERNS = (
    r"в двух словах",
    r"вкратце",
    r"кратко",
    r"кратенько",
    r"без лишнего",
    r"не растекайся",
    r"не растекаться",
    r"без воды",
    r"без простыни",
    r"коротко",
)

_MORE_RE = re.compile(
    "|".join(f"(?:{pattern})" for pattern in _MORE_DETAIL_PATTERNS),
    re.IGNORECASE,
)
_BRIEF_RE = re.compile(
    "|".join(f"(?:{pattern})" for pattern in _BRIEF_PATTERNS),
    re.IGNORECASE,
)


def detect_detail_level(message: str) -> str:
    """Return ``"detailed"`` | ``"brief"`` | ``"normal"`` from explicit phrasing.

    "more detail" wins over "brief" when both appear — the stronger, more
    specific request takes precedence.
    """
    text = message or ""
    if _MORE_RE.search(text):
        return "detailed"
    if _BRIEF_RE.search(text):
        return "brief"
    return "normal"
