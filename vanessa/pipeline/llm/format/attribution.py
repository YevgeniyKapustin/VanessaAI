"""Strip "X asked me to pass on" framing from a relayed message.

The owner wants the other chat to get the information itself, not a report
that he asked Vanessa to send it. The compose prompt forbids the framing;
this module is the deterministic safety net for the common phrasings.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

_VERBS = (
    r"(?:просит|просил|просила|попросил|попросила|сказал|сказала|"
    r"говорит|сообщает|уточняет|решил|решила)"
)
_PASS = r"(?:передать|передаёт|передает|сказать|сообщить|уточнить|ответить|написать)"
_SEP = r"\s*,?\s*(?:что|чтобы)?\s*[:,—–-]?\s*"

_GENERIC = (
    re.compile(r"^\s*(?:передаю|передаёт|передает)\s+(?:от|со\s+слов)\s+[^:,—–-]{1,40}\s*[:,—–-]?\s*", re.I),
    re.compile(r"^\s*(?:по|с)\s+(?:просьбе|поручению|разрешения)\s+[^:,—–-]{1,40}\s*[:,—–-]?\s*", re.I),
    re.compile(
        rf"^\s*[A-ZА-ЯЁ][\w'-]{{1,30}}\s+{_VERBS}\s*(?:{_PASS})?{_SEP}"
    ),
    re.compile(
        r"^\s*[A-Z][\w'-]{1,30}\s+(?:asks|asked|says|said|wants|wanted|told|tells)"
        r"\s+(?:me\s+)?(?:to\s+)?(?:pass(?:\s+on)?|say|tell|write|send|answer)?"
        r"\s*[:,—–-]?\s*",
        re.I,
    ),
)


def _named_patterns(name: str) -> tuple[re.Pattern[str], ...]:
    escaped = re.escape(name)
    return (
        re.compile(rf"^\s*от\s+{escaped}\s*[:,—–-]\s*", re.I),
        re.compile(rf"^\s*{escaped}\s*[:,—–-]\s*", re.I),
        re.compile(rf"^\s*{escaped}\s+{_VERBS}\s*(?:{_PASS})?{_SEP}", re.I),
    )


def _strip_all(
    text: str,
    patterns: tuple[re.Pattern[str], ...],
) -> str:
    cleaned = text.strip()
    for pattern in patterns:
        stripped = pattern.sub("", cleaned, count=1).strip()
        if stripped != cleaned:
            return stripped
    return cleaned


def _named_patterns_for(names: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    patterns: list[re.Pattern[str]] = []
    for name in sorted(
        {name.strip() for name in names if name and name.strip()},
        key=len,
        reverse=True,
    ):
        patterns.extend(_named_patterns(name))
    return tuple(patterns)


def strip_attribution(text: str, names: Sequence[str]) -> str:
    """Remove a leading owner-attribution phrase; keep the substance."""
    cleaned = _strip_all(text, _GENERIC)
    return _strip_all(cleaned, _named_patterns_for(names))
