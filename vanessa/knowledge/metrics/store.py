"""MetricsStore: persist mood & relationship snapshots in the vault.

The single source of truth is the person card: a nested ``metrics`` dict in its
frontmatter (fast read for decision/tone feedback, portraits and pipeline
merges). There is deliberately no separate time-series store under ``Metrics/``.

Every chat participant gets a person card with a zero baseline from their very
first message; the LLM planner (Vanessa) then moves values off zero over time.
Writes are fail-open and serialized through the vault's shared asyncio lock.
"""

from __future__ import annotations

from vanessa.knowledge.format import (
    PEOPLE,
    TYPE_PERSON,
    today,
)
from vanessa.knowledge.index.index import KnowledgeIndex
from vanessa.knowledge.metrics.schema import MetricsSnapshot, PersonMetrics
from vanessa.knowledge.metrics.store_resolve import (
    fallback_person_id,
    id_from_telegram_index,
    valid_telegram_id,
)
from vanessa.knowledge.metrics.store_write import (
    log_snapshot_stored,
    snapshot_paths,
    zero_if_new,
)
from vanessa.knowledge.people.people import canonicalize_person
from vanessa.knowledge.schema import VaultNote
from vanessa.knowledge.store.vault import KnowledgeVault


class MetricsStore:
    def __init__(
        self,
        vault: KnowledgeVault,
        index: KnowledgeIndex | None = None,
    ) -> None:
        self._vault = vault
        self._index = index or KnowledgeIndex(vault)

    async def store_snapshot(self, snapshot: MetricsSnapshot) -> str | None:
        """Persist a snapshot. Returns the person card path or None on skip."""
        if not self._vault.is_configured:
            return None
        person_id = await self._resolve_person(snapshot)
        if not person_id:
            return None
        rel = f"{PEOPLE}/{person_id}.md"
        note = await self._vault.read_note(rel)
        snapshot = zero_if_new(snapshot, note)
        card, created_card = await self._store_card_snapshot(
            person_id, snapshot, note
        )
        log_snapshot_stored(person_id, snapshot_paths(card, created_card=created_card))
        return card

    async def _resolve_person(self, snapshot: MetricsSnapshot) -> str:
        people_index = await self._index.load_folder(PEOPLE)
        return canonicalize_person(snapshot.person, snapshot.telegram_id, people_index)

    async def _store_card_snapshot(
        self,
        person_id: str,
        snapshot: MetricsSnapshot,
        note: VaultNote | None,
    ) -> tuple[str | None, bool]:
        """Merge the snapshot into the person card. Returns (path, created)."""
        rel = f"{PEOPLE}/{person_id}.md"
        if note is None:
            name = snapshot.name or snapshot.person or person_id
            meta: dict = {
                "type": TYPE_PERSON,
                "id": person_id,
                "aliases": [name] if name else [person_id],
                "created": today(),
                "updated": today(),
                "metrics": snapshot.metrics.to_dict(),
            }
            if snapshot.telegram_id is not None:
                meta["telegram_id"] = snapshot.telegram_id
            rel = await self._vault.write_note(
                rel,
                meta,
                self._person_template(),
                mutation_source="metrics",
            )
            await self._index.rebuild_folder(PEOPLE)
            return rel, True
        meta = dict(note.meta)
        existing = meta.get("metrics")
        if not isinstance(existing, dict):
            existing = {}
        merged = {**existing, **snapshot.metrics.to_dict()}
        meta["metrics"] = merged
        meta["updated"] = today()
        rel = await self._vault.write_note(
            rel, meta, note.body, mutation_source="metrics"
        )
        return rel, False

    @staticmethod
    def _person_template() -> str:
        return (
            "## Контекст жизни\n\n"
            "## Цитатник\n\n"
            "## Хроника"
        )

    async def load_snapshot(self, person_id: str) -> PersonMetrics | None:
        """Read the current snapshot from the person card frontmatter."""
        rel = f"{PEOPLE}/{person_id}.md"
        note = await self._vault.read_note(rel)
        if note is None:
            return None
        data = note.meta.get("metrics")
        if not isinstance(data, dict):
            return None
        return PersonMetrics.from_dict(data)

    async def resolve_person_id(self, person: str, telegram_id: int | None) -> str:
        """Map a free-form person reference to a stable card id."""
        people_index = await self._index.load_folder(PEOPLE)
        return canonicalize_person(person, telegram_id, people_index)

    async def resolve_by_telegram_id(
        self,
        telegram_id: int,
        *,
        name: str | None = None,
    ) -> str:
        """Map a telegram id to a stable card id via the People index.

        Resolution order: existing card (index) -> canonical nickname roster ->
        an existing card matched by display name -> stable ``user-<id>``
        fallback. The fallback guarantees even a brand-new participant resolves
        to a card that will hold their zero-baseline metrics after one message.
        """
        if not valid_telegram_id(telegram_id):
            return ""
        people_index = await self._index.load_folder(PEOPLE)
        person_id = id_from_telegram_index(people_index, telegram_id)
        if person_id:
            return person_id
        return fallback_person_id(people_index, telegram_id, name)
