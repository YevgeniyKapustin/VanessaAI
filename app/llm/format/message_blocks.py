"""Model-marked reply block splitter.

The compose model is instructed to split long replies into several short
messages (blocks) of 1-2 sentences each, separated by a marker line ``[next]``
on its own line (no marker after the last block). This module turns a finished
reply into the messages the bot actually sends:

- ``split_reply_into_blocks`` — the list of messages to deliver (marker-aware);
- ``strip_block_markers`` — the marker-free full text (stored in the DB / used
  for metrics), so markers never leak into the conversation history.

Robustness mirrors ``answer_tag``: a ``[next]`` inside a fenced code block is
NOT a separator. If the model never emits markers (older prompt / refusal) the
reply is split deterministically on sentence/paragraph boundaries instead, and
every block is hard-capped at ``max_chars`` (Telegram's 4096-char limit).
"""

from __future__ import annotations

import re

DEFAULT_BLOCK_MARKER = "[next]"

_FENCED_CODE = re.compile(r"```[\s\S]*?```", re.DOTALL)
# Paragraph / sentence boundaries — used by the deterministic fallback splitter.
_PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+")


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


def _drop_marker_lines(segment: str, marker: str) -> str:
    lines = [
        line
        for line in segment.splitlines(keepends=True)
        if not _is_marker_line(line, marker)
    ]
    return "".join(lines)


def strip_block_markers(reply: str, *, marker: str = DEFAULT_BLOCK_MARKER) -> str:
    """Remove the ``[next]`` marker lines from a reply, keeping content intact."""
    text = reply or ""
    return _map_outside_fences(text, lambda s: _drop_marker_lines(s, marker)).strip()


def _split_on_markers(text: str, marker: str) -> list[str]:
    """Split ``text`` into blocks on marker lines (code-fence-safe).

    A fenced code block is treated as one atomic unit attached to the current
    block, so a ``[next]`` inside code is never a separator.
    """
    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            blocks.append("\n".join(current))
            current.clear()

    def consume_segment(segment: str) -> None:
        for line in segment.splitlines():
            if _is_marker_line(line, marker):
                flush()
            else:
                current.append(line)

    cursor = 0
    for match in _FENCED_CODE.finditer(text):
        if match.start() > cursor:
            consume_segment(text[cursor : match.start()])
        current.append(match.group(0))
        cursor = match.end()
    if cursor < len(text):
        consume_segment(text[cursor:])
    flush()
    return [block.strip() for block in blocks if block.strip()]


def _split_prose_units(prose: str) -> list[str]:
    """Paragraphs (blank-line separated) further split into sentences.

    Splitting on newlines/sentences — not just hard char caps — keeps blocks on
    natural boundaries even when the model omits punctuation (common in casual
    chat), so the fallback rarely produces one giant wall of text.
    """
    units: list[str] = []
    for paragraph in _PARAGRAPH_BOUNDARY.split(prose):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        units.extend(_SENTENCE_BOUNDARY.split(paragraph))
    return units


def _split_units(text: str) -> list[str]:
    """Semantic units for the deterministic fallback (code fences stay atomic)."""
    units: list[str] = []
    cursor = 0
    for match in _FENCED_CODE.finditer(text):
        if match.start() > cursor:
            units.extend(_split_prose_units(text[cursor : match.start()]))
        units.append(match.group(0))
        cursor = match.end()
    if cursor < len(text):
        units.extend(_split_prose_units(text[cursor:]))
    return [unit.strip() for unit in units if unit.strip()]


def _chunk_words(unit: str, size: int) -> list[str]:
    """Split an over-long unit into word chunks of at most ``size`` chars."""
    if len(unit) <= size:
        return [unit]
    chunks: list[str] = []
    current = ""
    for word in unit.split():
        if current and len(current) + len(word) + 1 > size:
            chunks.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        chunks.append(current)
    return chunks


def _sentence_fallback(
    text: str,
    *,
    max_chars: int,
    target_chars: int,
) -> list[str]:
    """Deterministic fallback splitter used when the model emitted no markers.

    Splits into paragraphs/sentences, hard-chunks any unit longer than
    ``target_chars`` on word boundaries, then packs the pieces into blocks of up
    to ``target_chars`` (never exceeding ``max_chars``). This guarantees a long
    reply never arrives as one wall of text even without any ``[next]`` markers
    or sentence punctuation. Never returns empty strings.
    """
    units = _split_units(text)
    pieces: list[str] = []
    for unit in units:
        for chunk in _chunk_words(unit, target_chars):
            if len(chunk) <= max_chars:
                pieces.append(chunk)
            else:
                pieces.extend(_chunk_words(chunk, max_chars))

    blocks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) + 1 > target_chars:
            blocks.append(current)
            current = piece
        else:
            current = f"{current}\n{piece}" if current else piece
    if current:
        blocks.append(current)
    return [block.strip() for block in blocks if block.strip()]


def split_reply_into_blocks(
    reply: str,
    *,
    marker: str = DEFAULT_BLOCK_MARKER,
    max_chars: int = 4096,
    fallback_target_chars: int = 900,
) -> list[str]:
    """Split a finished reply into the Telegram messages to send.

    Prefers the model's explicit ``[next]`` markers; falls back to a
    deterministic sentence-aware split when none are present. Every block is
    hard-capped at ``max_chars`` (Telegram's 4096-char message limit).
    """
    text = reply or ""
    if not text.strip():
        return []

    marker_blocks = _split_on_markers(text, marker)
    if marker_blocks and len(marker_blocks) > 1:
        result: list[str] = []
        for block in marker_blocks:
            if len(block) > max_chars:
                result.extend(
                    _sentence_fallback(
                        block,
                        max_chars=max_chars,
                        target_chars=fallback_target_chars,
                    )
                )
            else:
                result.append(block)
        return [block for block in result if block]

    # No explicit blocks (single reply or the model skipped markers): apply the
    # deterministic splitter so long replies still arrive as several messages.
    return _sentence_fallback(
        text,
        max_chars=max_chars,
        target_chars=fallback_target_chars,
    )
