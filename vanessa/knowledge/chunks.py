"""Deterministic chunking for People dossiers.

A person's card can hold a long chronological dossier (dozens of dated fact
lines). For "reveal the person in detail" retrieval we want to rank the dossier's
internal text blocks by embedding similarity, not just inject the compact LLM
portrait or one bounded raw dump. This module splits a dossier body into stable,
human-readable blocks; the vector indexer embeds each block separately and the
retriever re-reads them by ``chunk_index``.
"""

from __future__ import annotations

import re

_PARAGRAPH_RE = re.compile(r"\n\s*\n")


def split_dossier_chunks(body: str, chunk_chars: int, overlap: int) -> list[str]:
    """Split a dossier body into at most ``chunk_chars``-sized text blocks.

    Short bodies (<= ``chunk_chars``) come back as a single block. Larger bodies
    are split on blank-line paragraph boundaries first, and paragraphs longer
    than ``chunk_chars`` are further split line-by-line. ``overlap`` carries the
    tail of the previous block into the next one so a fact spanning a boundary
    stays readable. Deterministic: the same input always yields the same blocks,
    which is what lets the retriever address a block by ``chunk_index``.
    """
    if chunk_chars <= 0 or not body or not body.strip():
        return [body.strip()] if body and body.strip() else []

    text = body.strip()
    if len(text) <= chunk_chars:
        return [text]

    paragraphs = [p.strip() for p in _PARAGRAPH_RE.split(text) if p.strip()]
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    for para in paragraphs:
        if len(para) > chunk_chars:
            flush()
            for piece in _split_long_paragraph(para, chunk_chars):
                if piece:
                    chunks.append(piece)
            continue
        if current and len(current) + 2 + len(para) > chunk_chars:
            flush()
        current = f"{current}\n\n{para}".strip() if current else para
    flush()

    if overlap > 0 and len(chunks) > 1:
        chunks = _apply_overlap(chunks, overlap)

    return [block.strip() for block in chunks if block.strip()]


def _split_long_paragraph(text: str, chunk_chars: int) -> list[str]:
    """Split a single oversized paragraph by lines, keeping lines intact."""
    lines = [line for line in text.splitlines() if line.strip()]
    chunks: list[str] = []
    current = ""
    for line in lines:
        if current and len(current) + 1 + len(line) > chunk_chars:
            chunks.append(current)
            current = ""
        current = f"{current}\n{line}".strip() if current else line
    if current:
        chunks.append(current)
    return chunks


def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
    """Prepend the tail of the previous block to each following block."""
    result = [chunks[0]]
    for index in range(1, len(chunks)):
        tail = _tail(chunks[index - 1], overlap)
        combined = f"{tail}\n\n{chunks[index]}".strip() if tail else chunks[index]
        result.append(combined)
    return result


def _tail(text: str, chars: int) -> str:
    """Last ``chars`` chars of ``text``, trimmed to a line boundary."""
    if chars <= 0 or len(text) <= chars:
        return ""
    tail = text[-chars:]
    newline = tail.find("\n")
    if 0 < newline < len(tail) - 1:
        tail = tail[newline + 1 :]
    return tail.lstrip()
