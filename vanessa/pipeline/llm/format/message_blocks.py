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
reply is split deterministically on sentence/paragraph boundaries instead —
each short unit is delivered as its own message (the same "several short
messages" shape the markers would produce, never one multi-line wall of text) —
and every block is hard-capped at ``max_chars`` (Telegram's 4096-char limit).
"""

from __future__ import annotations

from vanessa.pipeline.llm.format.block_fallback import _sentence_fallback
from vanessa.pipeline.llm.format.block_markers import (
    DEFAULT_BLOCK_MARKER,
    _is_marker_line,
    _keep_nonempty,
    _strip_marker_tokens,
    strip_block_markers,
)
from vanessa.pipeline.llm.format.code_fences import FENCED_CODE as _FENCED_CODE


def _flush_current_block(blocks: list[str], current: list[str]) -> None:
    if current:
        blocks.append("\n".join(current))
        current.clear()


def _consume_marker_segment(
    segment: str,
    marker: str,
    blocks: list[str],
    current: list[str],
) -> None:
    for line in segment.splitlines():
        if _is_marker_line(line, marker):
            _flush_current_block(blocks, current)
        else:
            current.append(line)


def _split_on_markers(text: str, marker: str) -> list[str]:
    """Split ``text`` into blocks on marker lines (code-fence-safe).

    A fenced code block is treated as one atomic unit attached to the current
    block, so a ``[next]`` inside code is never a separator.
    """
    blocks: list[str] = []
    current: list[str] = []
    cursor = 0
    for match in _FENCED_CODE.finditer(text):
        if match.start() > cursor:
            _consume_marker_segment(
                text[cursor : match.start()], marker, blocks, current
            )
        current.append(match.group(0))
        cursor = match.end()
    if cursor < len(text):
        _consume_marker_segment(text[cursor:], marker, blocks, current)
    _flush_current_block(blocks, current)
    return _keep_nonempty(blocks)


def _sanitize_delivered(blocks: list[str], marker: str) -> list[str]:
    # Sanitize every delivered block so an inline or truncated `[next]` the
    # model left behind (e.g. the output cap hit mid-marker) never reaches
    # the chat as a literal control tag.
    return [
        block
        for block in (_strip_marker_tokens(b, marker).strip() for b in blocks)
        if block
    ]


def _blocks_from_markers(
    marker_blocks: list[str],
    max_chars: int,
    fallback_target_chars: int,
) -> list[str]:
    result: list[str] = []
    for block in marker_blocks:
        if len(block) <= max_chars:
            result.append(block)
            continue
        result.extend(
            _sentence_fallback(
                block,
                max_chars=max_chars,
                target_chars=fallback_target_chars,
            )
        )
    return result


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
    if len(marker_blocks) > 1:
        return _sanitize_delivered(
            _blocks_from_markers(
                marker_blocks, max_chars, fallback_target_chars
            ),
            marker,
        )

    # No explicit blocks (single reply or the model skipped markers): apply the
    # deterministic splitter so long replies still arrive as several messages.
    # Marker tokens are stripped FIRST: when the reply is cut off by the output
    # limit right after emitting `[next]` (a dangling, truncated or inline
    # marker), the fallback must never deliver that control marker as a real
    # chat message. The post-sanitize below is a belt-and-braces guarantee.
    return _sanitize_delivered(
        _sentence_fallback(
            strip_block_markers(text, marker=marker),
            max_chars=max_chars,
            target_chars=fallback_target_chars,
        ),
        marker,
    )
