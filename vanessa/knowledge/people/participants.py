"""ParticipantsDigest: compact per-participant summary for the planner prompt.

The query-composition model needs to know the chat participants — not just
their nicknames, but what Vanessa knows about each of them (mood, recent facts)
from the People dossiers she updates regularly. This helper turns those cards
into a short, token-friendly block injected into the ``{participants}``
placeholder of the planner prompt, so the model composes queries that
reference the right aliases and topics.

To keep the planner prompt lean, the digest is now *dynamic*: instead of dumping
every participant (up to ``max_people`` x several facts) on every turn, it
renders only the people mentioned in the current message + the recent window
(sliding-context filtering), and falls back to a small ``min_people`` floor when
nothing is mentioned so the model still has disambiguation anchors. The per
-person rendering is cached by People-card mtime; only the selection is
recomputed per request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vanessa.config import settings
from vanessa.core.messages import ContextMessage
from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.people.entities import resolve_mentioned_people
from vanessa.knowledge.people.participants_select import (
    cap_people,
    fill_to_floor,
    person_line_from_note,
    unique_people_files,
)
from vanessa.knowledge.store.vault import KnowledgeVault

if TYPE_CHECKING:
    from vanessa.knowledge.index.index import KnowledgeIndex


class ParticipantsDigest:
    def __init__(
        self,
        vault: KnowledgeVault,
        index: KnowledgeIndex | None = None,
        *,
        max_people: int | None = None,
        max_facts: int | None = None,
        recent_window: int | None = None,
        min_people: int | None = None,
    ) -> None:
        self._vault = vault
        if index is None:
            from vanessa.knowledge.index.index import (  # noqa: PLC0415
                KnowledgeIndex,
            )

            index = KnowledgeIndex(vault)
        self._index = index
        self._max_people = (
            max_people
            if max_people is not None
            else settings.knowledge_participant_max_people
        )
        self._max_facts = (
            max_facts
            if max_facts is not None
            else settings.knowledge_participant_max_facts
        )
        self._recent_window = (
            recent_window
            if recent_window is not None
            else settings.knowledge_participant_recent_window
        )
        self._min_people = (
            min_people
            if min_people is not None
            else settings.knowledge_participant_min_people
        )
        # Cached per (People-mtime): rendered lines by file + ordered file list.
        self._cache_lines: dict[str, str] | None = None
        self._cache_files: list[str] = []
        self._cache_key: tuple = ()

    async def build(
        self,
        message: str = "",
        recent_messages: list[ContextMessage] | None = None,
        sender_name: str = "",
    ) -> str:
        """Return the digest for the people relevant to this turn.

        People mentioned in the current message come first, then people from the
        recent window; when nothing is mentioned a small fallback floor keeps
        the digest non-empty. The rendered lines are cached until any People
        note changes; only the selection is recomputed per request.
        """
        if not self._vault.is_configured:
            return ""
        people_index = await self._index.load_folder(PEOPLE)
        signature = await self._vault.notes_signature(PEOPLE)
        if self._cache_lines is None or signature != self._cache_key:
            lines, files = await self._build_person_lines(people_index)
            self._cache_lines = lines
            self._cache_files = files
            self._cache_key = signature
        selected = self._select(
            self._cache_files,
            people_index,
            message,
            recent_messages,
            sender_name,
        )
        return "\n".join(
            self._cache_lines[file] for file in selected if file in self._cache_lines
        )

    def _select(
        self,
        files: list[str],
        people_index: dict,
        message: str,
        recent_messages: list[ContextMessage] | None,
        sender_name: str = "",
    ) -> list[str]:
        """Ordered selection: mentioned people first, then the fallback floor."""
        mentioned = resolve_mentioned_people(
            message,
            recent_messages,
            people_index,
            recent_window=self._recent_window,
            sender_name=sender_name,
        )
        known = set(files)
        selected = [file for file in mentioned if file in known]
        fill_to_floor(selected, files, max(self._min_people, 0))
        return cap_people(selected, self._max_people)

    async def _person_line_for(self, file: str) -> str:
        note = await self._vault.read_note(file)
        return person_line_from_note(note, self._max_facts)

    async def _build_person_lines(
        self,
        people_index: dict,
    ) -> tuple[dict[str, str], list[str]]:
        """Render every People card to a one-line summary; returns line + order."""
        aliases = people_index.get("aliases")
        if not isinstance(aliases, dict):
            return {}, []
        lines: dict[str, str] = {}
        files: list[str] = []
        for file in sorted(unique_people_files(aliases)):
            line = await self._person_line_for(file)
            if not line:
                continue
            lines[file] = line
            files.append(file)
        return lines, files
