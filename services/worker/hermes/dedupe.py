"""Skip a Hermes ask that repeats a job still open in the same chat.

The planner turns a correction («не, я имею в виду глянь») into almost the
same Hermes question. Two jobs then post two near-duplicate follow-ups. A
job is open from ``handle()`` until its follow-up is posted.

Similarity: word stems (first ``STEM_CHARS`` letters of words with at least
``MIN_WORD_CHARS`` letters). A new question repeats an open one when they
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


def is_rephrase(new: frozenset[str], open_question: frozenset[str]) -> bool:
    shared = len(new & open_question)
    if shared < MIN_SHARED:
        return False
    return shared / min(len(new), len(open_question)) >= OVERLAP_RATIO


class OpenAsks:
    """Question stems of the open jobs, per chat (this worker process only)."""

    def __init__(self) -> None:
        self._by_key: dict[object, tuple[int, frozenset[str]]] = {}

    def repeats(self, chat_id: int, question: str) -> bool:
        stems = question_stems(question)
        return any(
            chat == chat_id and is_rephrase(stems, open_stems)
            for chat, open_stems in self._by_key.values()
        )

    def add(self, key: object, chat_id: int, question: str) -> None:
        self._by_key[key] = (chat_id, question_stems(question))

    def discard(self, key: object) -> None:
        self._by_key.pop(key, None)
