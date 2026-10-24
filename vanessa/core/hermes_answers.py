"""Work lookups Vanessa answered lately, per chat (this agent process only).

Right after a lookup result is posted, a mere reaction to it («ну и …»)
can make the planner ask the same question again. ``covers`` tells the
Retrieve stage that the answer is already in the chat, so no new lookup
runs. It holds when all of this is true:

- the result for a rephrase of the new question was posted in this chat
  less than ``window_seconds`` ago;
- the user's own message shares no stem with the new question, so the
  planner built the question from the context only.

A real new question still asks: another topic is no rephrase, and a
message that names the topic again («а что сейчас с деплоем?») shares a
stem with the question.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from vanessa.core.question_stems import is_rephrase, question_stems

#: Answers kept per chat (the newest ones).
MAX_PER_CHAT = 8

type _Answer = tuple[float, frozenset[str]]


class RecentAnswers:
    """Question stems of the lookup results posted lately, per chat."""

    def __init__(
        self,
        *,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window = window_seconds
        self._clock = clock
        self._by_chat: dict[int, list[_Answer]] = {}

    def note(self, chat_id: int, question: str) -> None:
        """Remember that the result for ``question`` was posted just now."""
        stems = question_stems(question)
        if not stems or self._window <= 0:
            return
        fresh = [*self._fresh(chat_id), (self._clock(), stems)]
        self._by_chat[chat_id] = fresh[-MAX_PER_CHAT:]

    def covers(self, chat_id: int, question: str, user_message: str) -> bool:
        """Whether a fresh result in this chat already answers ``question``."""
        asked = question_stems(question)
        if question_stems(user_message) & asked:
            return False
        return any(is_rephrase(asked, stems) for _, stems in self._fresh(chat_id))

    def _fresh(self, chat_id: int) -> list[_Answer]:
        oldest = self._clock() - self._window
        return [entry for entry in self._by_chat.get(chat_id, []) if entry[0] >= oldest]
