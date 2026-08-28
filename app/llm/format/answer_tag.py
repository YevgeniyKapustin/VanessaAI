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
# Explicit "this is a repeat, stay silent" tag the compose model emits INSTEAD
# of an `[answer]` + message. A dedicated tag is a far more robust refusal
# signal than an empty reply — the model never has to produce a blank message.
IGNORE_MARKER = "[ignore]"
_IGNORE_TAG = re.compile(r"\[\s*ignore\s*\]", re.IGNORECASE)
# Angle-bracket `<answer>...</answer>` markup some reasoning models emit as
# "thinking" instead of the bracket tag. The content INSIDE is the real reply;
# the tags themselves must never reach the chat.
_ANGLE_ANSWER_PAIR = re.compile(
    r"<\s*answer\s*>(.*?)<\s*/\s*answer\s*>",
    re.IGNORECASE | re.DOTALL,
)
# Any residual ANSWER control token — stripped from the delivered reply as a
# final safety net, whatever exact form the model emitted. `[ignore]` is
# deliberately NOT here: it is handled by the refusal path (`has_ignore_marker`)
# as a line-leading signal, while an inline `[ignore]` inside a sentence is
# legitimate content («он написал [ignore] в чате») and must be preserved.
_CONTROL_TOKEN = re.compile(
    r"\[\s*answer\s*\]|<\s*/?\s*answer\s*>",
    re.IGNORECASE,
)


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


def _map_outside_fences(text: str, mapper) -> str:
    """Apply ``mapper`` to every non-code segment, keeping code fences intact."""
    parts: list[str] = []
    cursor = 0
    for match in _FENCED_CODE.finditer(text):
        if match.start() > cursor:
            parts.append(mapper(text[cursor : match.start()]))
        parts.append(match.group(0))
        cursor = match.end()
    if cursor < len(text):
        parts.append(mapper(text[cursor:]))
    return "".join(parts)


def strip_control_tags(text: str) -> str:
    """Remove residual ANSWER control tags from ``text``, outside code fences.

    Strips ``[answer]`` and the angle-bracket ``<answer>`` / ``</answer>``
    variants a reasoning model may emit instead of the bracket tag (thinking-style
    markup) — whatever survives the provider's split must never reach the chat.
    ``[ignore]`` is NOT stripped (inline it is content, and the refusal path
    already handles real markers upstream), and neither is the ``[next]`` block
    marker, which belongs to the block splitter (``message_blocks``) and is needed
    there to separate the delivered messages.
    """
    return _map_outside_fences(
        text or "",
        lambda s: _CONTROL_TOKEN.sub("", s),
    ).strip()


def extract_answer(raw: str) -> tuple[str, str]:
    """Split raw model output into ``(final_reply, reasoning)``.

    The final reply is the text after the last ``[answer]`` tag (stripped of
    surrounding whitespace); the reasoning is everything before it (also without
    the tag). A reasoning model may also emit the answer as ``<answer>...</answer>``
    markup — the content inside is taken as the reply. Without any tag the whole
    output is returned as the reply. Residual control tags are stripped from the
    reply as a final safety net so they never reach the chat.
    """
    text = raw or ""
    if not text.strip():
        return "", ""

    # The bracket `[answer]` tag is the primary split signal and wins over the
    # angle-bracket form: a stray `<answer>...</answer>` inside a properly tagged
    # reply is then just residual markup stripped from the reply, never the reply
    # itself.
    span = _last_tag_span(text)
    if span is not None:
        start, end = span
        reasoning = text[:start].strip()
        final_reply = text[end:].strip()
        return strip_control_tags(final_reply), reasoning

    # `<answer>...</answer>` markup (thinking-style output, no bracket tag): the
    # inner content is the reply, the tags and everything around them is reasoning.
    angle = _ANGLE_ANSWER_PAIR.search(text)
    if angle is not None:
        reply = angle.group(1).strip()
        reasoning = (text[: angle.start()] + text[angle.end() :]).strip()
        return strip_control_tags(reply), reasoning

    return strip_control_tags(text.strip()), ""


def has_ignore_marker(text: str) -> bool:
    """True when the compose output contains a standalone ``[ignore]`` marker.

    The compose model is instructed to output the ``[ignore]`` tag (instead of
    the ``[answer]`` tag + a message) when the user repeats the same message and
    no reply is needed, optionally followed by a short internal reason on the
    same line (e.g. ``[ignore] повтор того же вопроса``) — the reason is only
    for debugging and never reaches the chat. Any line that STARTS with the tag
    (whitespace-tolerant, case-insensitive) counts: normally the whole output is
    just the marker, but a missing ``[answer]`` tag makes the reasoning land in
    the reply, so a lone marker line anywhere is still treated as a refusal
    signal. A marker embedded inside a sentence ("он написал [ignore] в чате")
    is NOT a refusal.
    """
    text = text or ""
    for line in text.splitlines():
        if _IGNORE_TAG.match(line.strip()):
            return True
    return False


def extract_ignore_reason(text: str) -> str:
    """Return the reason written after a standalone ``[ignore]`` marker, if any.

    The model may append a short internal reason on the same line as the tag
    (``[ignore] повтор``) purely for debugging — it is never delivered to the
    chat. Returns the stripped reason text, or ``""`` when there is no marker or
    no text after it.
    """
    text = text or ""
    for line in text.splitlines():
        stripped = line.strip()
        match = _IGNORE_TAG.match(stripped)
        if match:
            return stripped[match.end():].strip()
    return ""
