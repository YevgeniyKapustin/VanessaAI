"""MetricsRetriever: fast read of a participant's metrics snapshot.

The decision gate and the compose prompt need the sender's current metrics
without scanning the vault. The snapshot lives in the person card frontmatter
and is resolved through the People index (``telegram_id -> card id``), then
parsed into ``PersonMetrics``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.index import KnowledgeIndex
from vanessa.knowledge.metrics.schema import PersonMetrics
from vanessa.knowledge.vault import KnowledgeVault

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SenderProfile:
    """A participant's card identity + current metrics + qualitative mood."""

    person_id: str
    metrics: PersonMetrics | None
    mood: str = ""

    @property
    def display_name(self) -> str:
        return self.person_id


class MetricsRetriever:
    def __init__(
        self,
        vault: KnowledgeVault,
        index: KnowledgeIndex | None = None,
    ) -> None:
        self._vault = vault
        self._index = index or KnowledgeIndex(vault)

    async def get_by_telegram_id(self, telegram_id: int) -> SenderProfile | None:
        """Return the sender's profile, or None when unknown/absent."""
        if not self._vault.is_configured or telegram_id is None or telegram_id <= 0:
            return None
        people_index = await self._index.load_folder(PEOPLE)
        entry = people_index.get("telegram_id", {}).get(str(telegram_id))
        if not isinstance(entry, dict):
            return None
        rel = entry.get("file")
        person_id = str(entry.get("id") or "")
        if not rel:
            return None
        return await self._read_profile(rel, person_id)

    async def get_by_person_id(self, person_id: str) -> SenderProfile | None:
        if not self._vault.is_configured or not person_id:
            return None
        return await self._read_profile(f"{PEOPLE}/{person_id}.md", person_id)

    async def _read_profile(self, rel: str, person_id: str) -> SenderProfile | None:
        note = await self._vault.read_note(rel)
        if note is None:
            return None
        data = note.meta.get("metrics")
        metrics = PersonMetrics.from_dict(data) if isinstance(data, dict) else None
        mood = str(note.meta.get("mood") or "")
        return SenderProfile(
            person_id=person_id or rel,
            metrics=metrics,
            mood=mood,
        )
