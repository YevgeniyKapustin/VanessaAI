from __future__ import annotations

import re

from vanessa.pipeline.llm.format.code_fences import (
    map_outside_fences as _map_outside_fences,
)

DEFAULT_BLOCK_MARKER = "[next]"


def _is_marker_line(line: str, marker: str) -> bool:
    """True when ``line`` is exactly the block marker (whitespace-tolerant).

    Both sides are normalized (whitespace stripped, lowercased), so ``[ Next ]``,
    ``[next]`` and ``[ NEXT ]`` all match the default ``[next]`` marker, while a
    differently-spelled tag is never treated as a separator for a custom marker.
    """
    stripped = line.strip()
    if not stripped:
        return False
    return (
        re.sub(r"\s+", "", stripped).lower()
        == re.sub(r"\s+", "", marker).lower()
    )


def _marker_token_regexes(marker: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Regexes matching a complete ``[next]`` token and a truncated unclosed tail
    (``[next`` / ``[Next `` left by an output cap), both whitespace/case tolerant.
    Fenced code is handled by the caller, never matched here.
    """
    core = re.escape(marker.strip("[]"))
    return (
        re.compile(rf"\[\s*{core}\s*\]", re.IGNORECASE),
        re.compile(rf"\[\s*{core}\s*$", re.IGNORECASE),
    )


def _clean_marker_line(
    raw_line: str,
    marker: str,
    complete: re.Pattern[str],
    truncated: re.Pattern[str],
) -> str | None:
    if _is_marker_line(raw_line, marker):
        return None
    body = raw_line.rstrip("\r\n")
    ending = raw_line[len(body):]
    cleaned = truncated.sub("", complete.sub("", body))
    # Keep structural blank lines; drop a line ONLY when it was pure
    # marker content (an inline `[next]` or a truncated `[next`).
    if not body.strip() or cleaned.strip():
        return re.sub(r" {2,}", " ", cleaned).rstrip() + ending
    return None


def _clean_marker_segment(
    segment: str,
    marker: str,
    complete: re.Pattern[str],
    truncated: re.Pattern[str],
) -> str:
    lines: list[str] = []
    for raw_line in segment.splitlines(keepends=True):
        cleaned_line = _clean_marker_line(raw_line, marker, complete, truncated)
        if cleaned_line is not None:
            lines.append(cleaned_line)
    return "".join(lines)


def _strip_marker_tokens(text: str, marker: str = DEFAULT_BLOCK_MARKER) -> str:
    """Remove ``[next]`` marker tokens from ``text``.

    Handles standalone marker lines (the normal case), inline markers the model
    put on a content line («блок [next] ещё») and truncated unclosed tails
    («[next» left when the output cap hits mid-marker) — so a control marker
    never reaches a delivered message or the stored history. Fenced code blocks
    are left untouched.
    """
    complete, truncated = _marker_token_regexes(marker)
    return _map_outside_fences(
        text,
        lambda segment: _clean_marker_segment(
            segment, marker, complete, truncated
        ),
    )


def strip_block_markers(reply: str, *, marker: str = DEFAULT_BLOCK_MARKER) -> str:
    """Remove the ``[next]`` marker tokens from a reply, keeping content intact.

    Removes standalone marker lines, inline markers and truncated unclosed tails
    (see ``_strip_marker_tokens``); fenced code blocks are left untouched.
    """
    text = reply or ""
    return _strip_marker_tokens(text, marker).strip()


def _keep_nonempty(blocks: list[str]) -> list[str]:
    return [block.strip() for block in blocks if block.strip()]
