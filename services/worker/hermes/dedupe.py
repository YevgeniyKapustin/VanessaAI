"""Skip a Hermes ask that repeats a job still open in the same chat.

The planner turns a correction («не, я имею в виду глянь») into almost the
same Hermes question. Two jobs then post two near-duplicate follow-ups. A
job is open from ``handle()`` until its follow-up is posted. The rephrase
check lives in ``vanessa.core.question_stems``.
"""

from __future__ import annotations

from vanessa.core.question_stems import is_rephrase, question_stems

__all__ = ["OpenAsks", "is_rephrase", "question_stems"]


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
