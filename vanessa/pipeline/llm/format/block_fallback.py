from __future__ import annotations

import re

from vanessa.pipeline.llm.format.block_markers import _keep_nonempty
from vanessa.pipeline.llm.format.code_fences import FENCED_CODE as _FENCED_CODE

# Paragraph / sentence boundaries — used by the deterministic fallback splitter.
_PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+")
_MAX_UNITS_PER_BLOCK = 2


def _split_prose_units(prose: str) -> list[str]:
    """Paragraphs (blank-line separated) further split into sentences.

    Splitting on newlines/sentences — not just hard char caps — keeps blocks on
    natural boundaries even when the model omits punctuation (common in casual
    chat), so the fallback rarely produces one giant wall of text.
    """
    units: list[str] = []
    for paragraph in _PARAGRAPH_BOUNDARY.split(prose):
        stripped = paragraph.strip()
        if not stripped:
            continue
        units.extend(_SENTENCE_BOUNDARY.split(stripped))
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


def _extend_chunk(current: str, word: str, size: int) -> tuple[str, str | None]:
    if current and len(current) + len(word) + 1 > size:
        return word, current
    joined = f"{current} {word}" if current else word
    return joined, None


def _split_oversize_unit(unit: str, size: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for word in unit.split():
        current, flushed = _extend_chunk(current, word, size)
        if flushed is not None:
            chunks.append(flushed)
    if current:
        chunks.append(current)
    return chunks


def _chunk_words(unit: str, size: int) -> list[str]:
    """Split an over-long unit into word chunks of at most ``size`` chars."""
    if len(unit) <= size:
        return [unit]
    return _split_oversize_unit(unit, size)


def _is_fenced_code(unit: str) -> bool:
    """True when ``unit`` is (or contains) a fenced code block."""
    return bool(_FENCED_CODE.search(unit))


def _fit_unit(unit: str, *, max_chars: int, target_chars: int) -> list[str]:
    fitted: list[str] = []
    for chunk in _chunk_words(unit, target_chars):
        if len(chunk) <= max_chars:
            fitted.append(chunk)
            continue
        fitted.extend(_chunk_words(chunk, max_chars))
    return fitted


def _cap_pieces(text: str, *, max_chars: int, target_chars: int) -> list[str]:
    pieces: list[str] = []
    for unit in _split_units(text):
        pieces.extend(_fit_unit(unit, max_chars=max_chars, target_chars=target_chars))
    return pieces


def _should_start_new_block(
    current: str,
    piece: str,
    current_count: int,
    target_chars: int,
    *,
    sticky: bool,
) -> bool:
    if not current or sticky:
        return False
    if current_count >= _MAX_UNITS_PER_BLOCK:
        return True
    return len(current) + len(piece) + 1 > target_chars


def _glue_piece(
    blocks: list[str],
    current: str,
    current_count: int,
    piece: str,
    target_chars: int,
) -> tuple[str, int]:
    sticky = _is_fenced_code(piece)
    if _should_start_new_block(
        current, piece, current_count, target_chars, sticky=sticky
    ):
        blocks.append(current)
        current = ""
        current_count = 0
    current = f"{current} {piece}" if current else piece
    # A code fence attaches to the surrounding block, not a countable unit.
    if not sticky:
        current_count += 1
    return current, current_count


def _sentence_fallback(
    text: str,
    *,
    max_chars: int,
    target_chars: int,
) -> list[str]:
    """Deterministic fallback splitter used when the model emitted no markers.

    Splits into paragraphs/sentences and delivers them as several short
    messages — the same "1-2 sentences per message" shape the ``[next]``
    markers would produce — instead of packing the whole reply into one
    multi-line wall of text. Consecutive short units are joined with a single
    space (never a newline) up to two per block; a fenced code block is glue,
    never a message boundary of its own (a code reply stays one message); any
    unit longer than ``target_chars`` (a run-on sentence, an unpunctuated
    paragraph) is hard-chunked on word boundaries; every block is capped at
    ``max_chars``. Never returns empty strings.
    """
    blocks: list[str] = []
    current = ""
    current_count = 0
    for piece in _cap_pieces(
        text, max_chars=max_chars, target_chars=target_chars
    ):
        current, current_count = _glue_piece(
            blocks, current, current_count, piece, target_chars
        )
    if current:
        blocks.append(current)
    return _keep_nonempty(blocks)
