"""Compare two work questions by word stems (rephrase check).

Similarity: word stems (first ``STEM_CHARS`` letters of words with at least
``MIN_WORD_CHARS`` letters). A new question repeats another one when they
share at least ``MIN_SHARED`` stems and ``OVERLAP_RATIO`` of the shorter
question's stems. Short function words («что», «как», «дай») drop out.
"""

from __future__ import annotations

import re

STEM_CHARS = 5
MIN_WORD_CHARS = 4
MIN_SHARED = 3
OVERLAP_RATIO = 0.6

_WORD_RE = re.compile(r"\w+")


def question_stems(text: str) -> frozenset[str]:
    words = _WORD_RE.findall(text.lower())
    return frozenset(word[:STEM_CHARS] for word in words if len(word) >= MIN_WORD_CHARS)


def is_rephrase(new: frozenset[str], other: frozenset[str]) -> bool:
    shared = len(new & other)
    if shared < MIN_SHARED:
        return False
    return shared / min(len(new), len(other)) >= OVERLAP_RATIO
