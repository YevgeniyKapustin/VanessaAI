"""ParticipantsDigest: compact per-participant summary for the planner prompt.

The query-composition model needs to know the chat participants — not just
their nicknames, but what Vanessa knows about each of them (mood, recent facts)
from the People dossiers she updates regularly. This helper turns those cards
into a short, token-friendly block injected into the ``{participants}``
placeholder of the planner prompt, so the model composes embedding queries that
reference the right aliases and topics.

To keep the planner prompt lean, the digest is now *dynamic*: instead of dumping
every participant (up to ``max_people`` × several facts) on every turn, it
renders only the people mentioned in the current message + the recent window
(sliding-context filtering), and falls back to a small ``min_people`` floor when
nothing is mentioned so the model still has disambiguation anchors. The per
-person rendering is cached by People-card mtime; only the selection is
recomputed per request.
"""

from __future__ import annotations

import re

from vanessa.config import settings
from vanessa.core.messages import ContextMessage
from vanessa.knowledge.entities import resolve_mentioned_people
from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.index import KnowledgeIndex
from vanessa.knowledge.vault import KnowledgeVault

_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}\s*[:\-]\s*")
_FACT_CAP = 140


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
        self._index = index or KnowledgeIndex(vault)
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
        known = {file for file in files}
        selected = [file for file in mentioned if file in known]

        floor = max(self._min_people, 0)
        for file in files:
            if len(selected) >= floor:
                break
            if file not in selected:
                selected.append(file)

        if self._max_people and len(selected) > self._max_people:
            return selected[: self._max_people]
        return selected

    async def _build_person_lines(
        self,
        people_index: dict,
    ) -> tuple[dict[str, str], list[str]]:
        """Render every People card to a one-line summary; returns line + order."""
        aliases = people_index.get("aliases")
        if not isinstance(aliases, dict):
            return {}, []

        seen_files: dict[str, str] = {}
        for alias, entry in aliases.items():
            if not isinstance(entry, dict):
                continue
            file = entry.get("file")
            if file and file not in seen_files:
                seen_files[file] = str(entry.get("id") or alias)

        lines: dict[str, str] = {}
        files: list[str] = []
        for file in sorted(seen_files):
            note = await self._vault.read_note(file)
            if note is None:
                continue
            line = self._format_person(note)
            if line:
                lines[file] = line
                files.append(file)
        return lines, files

    def _format_person(self, note) -> str:
        meta = note.meta or {}
        person_id = str(meta.get("id") or note.relative_path)
        nickname = str(meta.get("nickname") or person_id)

        aliases = meta.get("aliases")
        alias_parts = [
            str(alias).strip()
            for alias in (aliases if isinstance(aliases, list) else [])
            if str(alias).strip().lower() != nickname.lower()
        ]
        alias_text = (
            f" (также {', '.join(alias_parts[:3])})" if alias_parts else ""
        )

        mood = str(meta.get("mood") or "").strip()
        mood_text = f", настроение: {mood}" if mood else ""

        facts = self._context_facts(note.body or "")[-self._max_facts :]
        facts_text = ""
        if facts:
            facts_text = ". Факты: " + "; ".join(facts)

        return f"{nickname}{alias_text}{mood_text}{facts_text}"

    @staticmethod
    def _context_facts(body: str) -> list[str]:
        """Bullets under ``## Контекст жизни``, newest last, date stripped."""
        facts: list[str] = []
        in_section = False
        for raw in body.splitlines():
            stripped = raw.strip()
            if stripped.startswith("## "):
                in_section = stripped == "## Контекст жизни"
                continue
            if not in_section or not stripped.startswith("- "):
                continue
            fact = stripped[2:].strip()
            fact = _DATE_PREFIX.sub("", fact).strip()
            if fact:
                if len(fact) > _FACT_CAP:
                    fact = fact[: _FACT_CAP - 1].rstrip() + "…"
                facts.append(fact)
        return facts
