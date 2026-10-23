"""Split a follow-up into short chat messages, like Vanessa's normal replies.

The model marks message breaks with ``[next]``; without markers the text is
split on sentences. The first block is the caption when a file goes along.
"""

from __future__ import annotations

from vanessa.config.content import get_content
from vanessa.contracts.outbound import MESSAGE_MAX_CHARS, MORE_TEXTS_MAX
from vanessa.pipeline.llm.format.message_blocks import split_reply_into_blocks
from vanessa.pipeline.llm.format.reply_format import strip_trailing_periods

#: The first message plus the most extra messages one outbound item carries.
MAX_BLOCKS = MORE_TEXTS_MAX + 1
_ELLIPSIS = "…"


def followup_blocks(text: str, *, marker: str | None = None) -> list[str]:
    """The messages to post, in order; empty for an empty text.

    More than ``MAX_BLOCKS`` blocks: the rest is dropped and the last kept
    block ends with «…».
    """
    marker = marker or get_content().llm.block_marker
    parts = split_reply_into_blocks(text, marker=marker, max_chars=MESSAGE_MAX_CHARS)
    blocks = [
        piece
        for part in parts
        for piece in _hard_cap(strip_trailing_periods(part).strip())
    ]
    if len(blocks) <= MAX_BLOCKS:
        return blocks
    kept = blocks[:MAX_BLOCKS]
    last = kept[-1][: MESSAGE_MAX_CHARS - len(_ELLIPSIS)].rstrip()
    kept[-1] = last + _ELLIPSIS
    return kept


def _hard_cap(block: str) -> list[str]:
    """Cut a block with no word break into pieces of one message each."""
    step = MESSAGE_MAX_CHARS
    return [block[start : start + step] for start in range(0, len(block), step)]
