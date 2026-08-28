"""Chain-of-thought answer splitter.

The compose model is instructed to think first (what from the context/archive is
useful, how to structure the reply), then emit the tag ``[answer]`` on its own
line, then the final message — the only part that reaches the chat. This module
splits the raw model output into ``(final_reply, reasoning)``:

- reasoning = everything before the tag (logged / traced for debugging, never sent);
- final_reply = everything after the tag (the actual message).

Robustness: the tag is matched case-insensitively (``[ANSWER]``/``[ Answer ]``)
and outside fenced code blocks, so a literal ``[answer]`` inside a code snippet
does not split the output. When the tag is missing the whole output is treated
as the final reply (a broken format never breaks the bot).
"""

from __future__ import annotations

import re

_FENCED_CODE = re.compile(r"```[\s\S]*?```", re.DOTALL)
# Tag like `[answer]`, `[ANSWER]`, `[ Answer ]`.
_ANSWER_TAG = re.compile(r"\[\s*answer\s*\]", re.IGNORECASE)


def _last_tag_span(text: str) -> tuple[int, int] | None:
    """``(start, end)`` of the last ``[answer]`` tag outside code fences, or None.

    Iterates the text in code / non-code segments so a ``[answer]`` inside a
    fenced code block is ignored; the final tag is the one that splits the reply.
    """
    last: tuple[int, int] | None = None
    cursor = 0
    for match in _FENCED_CODE.finditer(text):
        if match.start() > cursor:
            found = _last_tag_span_in_segment(text[cursor : match.start()])
            if found is not None:
                last = (cursor + found[0], cursor + found[1])
        cursor = match.end()
    if cursor < len(text):
        found = _last_tag_span_in_segment(text[cursor:])
        if found is not None:
            last = (cursor + found[0], cursor + found[1])
    return last


def _last_tag_span_in_segment(segment: str) -> tuple[int, int] | None:
    """Span of the last ``[answer]`` tag within a non-code segment, or None."""
    matches = list(_ANSWER_TAG.finditer(segment))
    if not matches:
        return None
    match = matches[-1]
    return match.start(), match.end()


def extract_answer(raw: str) -> tuple[str, str]:
    """Split raw model output into ``(final_reply, reasoning)``.

    The final reply is the text after the last ``[answer]`` tag (stripped of
    surrounding whitespace); the reasoning is everything before it (also without
    the tag). Without a tag the whole output is returned as the reply with empty
    reasoning.
    """
    text = raw or ""
    if not text.strip():
        return "", ""

    span = _last_tag_span(text)
    if span is None:
        return text.strip(), ""

    start, end = span
    reasoning = text[:start].strip()
    final_reply = text[end:].strip()
    return final_reply, reasoning
