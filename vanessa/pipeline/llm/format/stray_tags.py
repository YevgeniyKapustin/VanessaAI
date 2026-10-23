"""Drop control-like tags the model invents (``[forward]``, ``[end]``).

Only a bare lowercase Latin ``[word]`` alone on a line or at a line end is
dropped: that is where the model puts markers like ``[next]``. Tags with
arguments (``[photo:1]``, ``[sticker:x]``), Cyrillic text in brackets and
fenced code are kept. Known markers (``[next]``, ``[ignore]``) are kept for
the stages that consume them.
"""

from __future__ import annotations

import re

from vanessa.pipeline.llm.format.code_fences import map_outside_fences

_TAIL_TAG = re.compile(r"(^|[ \t])\[\s*([a-z][a-z_-]{1,19})\s*\][ \t]*$", re.MULTILINE)
_KEPT = frozenset({"next", "ignore"})


def _drop(match: re.Match[str], kept: frozenset[str]) -> str:
    if match.group(2) in kept:
        return match.group(0)
    return ""


def strip_stray_tags(text: str, *, keep: tuple[str, ...] = ()) -> str:
    """Remove invented ``[word]`` tags at a line end, outside code fences."""
    kept = _KEPT | {tag.strip("[] ").lower() for tag in keep}
    return map_outside_fences(
        text or "",
        lambda segment: _TAIL_TAG.sub(lambda m: _drop(m, kept), segment),
    )
