"""KnowledgeVaultWriter: apply MemoryPlan updates with merge semantics.

Each update targets a stable file (person card, glossary entry, culture
recommendation) or an append-only dated file (events, weekly logs). Merges are
idempotent: quote/fact lines are deduped and ``source_message_ids`` accumulate,
so the post-reply stage and the periodic sweep never duplicate content.
"""

from __future__ import annotations

import logging

from vanessa.infrastructure.observability.tracing import get_tracer
from vanessa.knowledge.index.index import KnowledgeIndex
from vanessa.knowledge.memory.writer_merge import WriterTemplates, merge_meta
from vanessa.knowledge.memory.writer_notes import WriterNoteUpdates
from vanessa.knowledge.memory.writer_people import WriterPeopleUpdates
from vanessa.knowledge.schema import MemoryPlan, VaultNote
from vanessa.knowledge.store.vault import KnowledgeVault
from vanessa.knowledge.vectors.vector_index import KnowledgeVectorIndexer

logger = logging.getLogger(__name__)


class KnowledgeVaultWriter(WriterPeopleUpdates, WriterNoteUpdates, WriterTemplates):
    def __init__(
        self,
        vault: KnowledgeVault,
        index: KnowledgeIndex | None = None,
        vector_indexer: KnowledgeVectorIndexer | None = None,
    ) -> None:
        self._vault = vault
        self._index = index or KnowledgeIndex(vault)
        self._vector_indexer = vector_indexer

    async def apply(
        self,
        plan: MemoryPlan,
        *,
        source_message_ids: list[int] | None = None,
        mutation_source: str = "post_reply_extract",
    ) -> int:
        """Apply plan updates. Returns the number of files written."""
        if not plan.updates or not self._vault.is_configured:
            return 0
        diffs: list[dict] = []
        self._mutation_source = mutation_source
        self._diffs = diffs
        changed_folders: set[str] = set()
        written_paths: list[str] = []
        await self._apply_plan_updates(
            plan, source_message_ids, changed_folders, written_paths
        )
        for folder in changed_folders:
            await self._index.rebuild_folder(folder)
            written_paths.append(f"{folder}/_index.yaml")
        await self._reindex_written(written_paths)
        tracer = get_tracer()
        async with tracer.span(
            name="finalize:extract_knowledge",
            metadata={"mutation_source": mutation_source},
            input={"updates": list(plan.updates)},
            output={"written": written_paths, "diff": diffs},
        ):
            pass
        logger.info(
            "knowledge_apply updates=%s written=%s folders=%s",
            len(plan.updates),
            len(written_paths),
            sorted(changed_folders),
        )
        return len(written_paths)

    async def _apply_plan_updates(
        self,
        plan: MemoryPlan,
        source_message_ids: list[int] | None,
        changed_folders: set[str],
        written_paths: list[str],
    ) -> None:
        for update in plan.updates:
            folder, paths = await self._apply_one_update(update, source_message_ids)
            if folder:
                changed_folders.add(folder)
                written_paths.extend(paths)

    async def _apply_one_update(
        self,
        update: object,
        source_message_ids: list[int] | None,
    ) -> tuple[str | None, list[str]]:
        if not isinstance(update, dict):
            return None, []
        try:
            return await self._apply_update(
                update,
                source_message_ids=source_message_ids,
            )
        except Exception:
            logger.exception("knowledge_update_failed update=%r", update)
            return None, []

    async def _reindex_written(self, written_paths: list[str]) -> None:
        if self._vector_indexer is None:
            return
        for path in written_paths:
            try:
                await self._vector_indexer.index_note(path)
            except Exception:
                logger.exception(
                    "knowledge_vector_reindex_failed path=%s",
                    path,
                )

    async def _apply_update(
        self,
        update: dict,
        source_message_ids: list[int] | None,
    ) -> tuple[str | None, list[str]]:
        handlers = {
            "quote": self._apply_quote,
            "person_mood": self._apply_person,
            "person_fact": self._apply_person,
            "glossary": self._apply_glossary,
            "event": self._apply_event,
            "recommendation": self._apply_recommendation,
            "weekly_summary": self._apply_weekly_summary,
        }
        handler = handlers.get(str(update.get("type") or "").strip())
        if handler is None:
            return None, []
        return await handler(update, source_message_ids)

    async def _write(
        self,
        relative_path: str,
        meta: dict,
        body: str,
        existing: VaultNote | None,
        source_message_ids: list[int] | None,
        *,
        keep_sources: bool = True,
    ) -> str:
        merged_meta = merge_meta(
            existing.meta if existing else {},
            meta,
            source_message_ids if keep_sources else None,
        )
        if not keep_sources:
            merged_meta.pop("source_message_ids", None)
        old_body = existing.body if existing else ""
        rel = await self._vault.write_note(
            relative_path,
            merged_meta,
            body,
            mutation_source=getattr(self, "_mutation_source", "direct"),
        )
        diffs = getattr(self, "_diffs", None)
        if diffs is not None and old_body != body:
            diffs.append(
                {
                    "path": rel,
                    "before": old_body,
                    "after": body,
                }
            )
        return rel
