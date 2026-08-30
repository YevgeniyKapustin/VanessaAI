"""Worker-side task handlers: one per ``TaskKind``.

Each handler owns the heavy work that used to run inside the API process —
embedding + Qdrant indexing, the knowledge sweep, portrait regeneration and
the knowledge-vector reindex — so it can be CPU/RAM-isolated in its own
container.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from vanessa.contracts.messages import TaskKind, TaskMessage

logger = logging.getLogger(__name__)


@dataclass
class WorkerAssembly:
    """The fully-built worker components (handlers + polling loops)."""

    handlers: dict[TaskKind, WorkerTaskHandler]
    sweep: Any | None = None
    portrait: Any | None = None


class WorkerTaskHandler(Protocol):
    async def handle(self, task: TaskMessage) -> None: ...


class IndexMessageHandler:
    """Embed a single message into Qdrant and persist the point id.

    Mirrors ``HybridSearchService.index`` (embed → upsert) without needing a
    message repository, and updates the message's stored point id afterwards.
    """

    def __init__(
        self,
        embeddings,
        vector_store,
        session_factory,
        *,
        max_retries: int = 2,
    ) -> None:
        self._embeddings = embeddings
        self._vector_store = vector_store
        self._session_factory = session_factory
        self._max_retries = max_retries

    async def handle(self, task: TaskMessage) -> None:
        payload = task.payload
        message_id = int(payload.get("message_id") or 0)
        role = str(payload.get("role") or "")
        content = str(payload.get("content") or "")
        point_id = payload.get("point_id")
        try:
            point = await self._index_with_retry(
                message_id, role, content, point_id
            )
        except Exception:
            logger.exception("worker_index_failed message_id=%s", message_id)
            return
        try:
            async with self._session_factory() as session:
                from vanessa.infrastructure.db.repository import MessageRepository

                await MessageRepository(session).update_qdrant_point_id(
                    message_id, point
                )
                await session.commit()
        except Exception:
            logger.exception(
                "worker_index_update_failed message_id=%s", message_id
            )

    async def _index_with_retry(
        self, message_id: int, role: str, content: str, point_id: Any
    ) -> str:
        from vanessa.core.messages import RAG_SOURCE_ROLE

        if role != RAG_SOURCE_ROLE:
            return point_id or ""
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                vector = await self._embeddings.embed(content)
                return await self._vector_store.upsert_message(
                    message_id=message_id,
                    role=role,
                    content=content,
                    vector=vector,
                    point_id=point_id,
                )
            except Exception as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                await asyncio.sleep(0.5 * (attempt + 1))
        assert last_error is not None
        raise last_error


class SweepHandler:
    """Run one knowledge-sweep cycle (messages newer than the cursor)."""

    def __init__(self, sweep, session_factory) -> None:
        self._sweep = sweep
        self._session_factory = session_factory

    async def handle(self, task: TaskMessage) -> None:
        async with self._session_factory() as session:
            from vanessa.infrastructure.db.repository import MessageRepository

            processed = await self._sweep.run(MessageRepository(session))
            logger.info("worker_sweep processed=%s", processed)


class PortraitHandler:
    """Regenerate stale person portraits."""

    def __init__(self, builder) -> None:
        self._builder = builder

    async def handle(self, task: TaskMessage) -> None:
        updated = await self._builder.run()
        logger.info("worker_portrait updated=%s", updated)


class ReindexKnowledgeHandler:
    """Rebuild the knowledge-vault vector collection."""

    def __init__(self, indexer) -> None:
        self._indexer = indexer

    async def handle(self, task: TaskMessage) -> None:
        await self._indexer.index_all()
        logger.info("worker_reindex_knowledge done")


class MemoryExtractHandler:
    def __init__(self, memory) -> None:
        self._memory = memory

    async def handle(self, task: TaskMessage) -> None:
        from vanessa.core.messages import context_message_from_payload

        payload = task.payload
        raw_messages = payload.get("messages") or []
        recent = [
            context_message_from_payload(item)
            for item in raw_messages
            if isinstance(item, dict)
        ]
        source_ids = [int(value) for value in (payload.get("source_message_ids") or [])]
        chat_id = payload.get("telegram_chat_id")
        await self._memory.run(
            recent_messages=recent,
            source_message_ids=source_ids or None,
            telegram_chat_id=int(chat_id) if chat_id is not None else None,
        )


class MetricsSnapshotHandler:
    def __init__(self, metrics, session_factory) -> None:
        self._metrics = metrics
        self._session_factory = session_factory

    async def handle(self, task: TaskMessage) -> None:
        from vanessa.infrastructure.db.repository import MessageRepository

        sender = task.payload.get("sender_telegram_id")
        only = {int(sender)} if sender is not None else None
        async with self._session_factory() as session:
            await self._metrics.run(
                MessageRepository(session),
                semantic=False,
                only_senders=only,
            )


class PhotoCaptionHandler:
    def __init__(self, captioner, session_factory) -> None:
        self._captioner = captioner
        self._session_factory = session_factory

    async def handle(self, task: TaskMessage) -> None:
        from vanessa.core.messages import ImageAttachment
        from vanessa.infrastructure.db.repository import MessageRepository

        message_id = int(task.payload.get("message_id") or 0)
        if not message_id:
            return
        async with self._session_factory() as session:
            repo = MessageRepository(session)
            record = await repo.get_by_id(message_id)
            if record is None or not record.attachments:
                return
            first = record.attachments[0]
            if not isinstance(first, dict) or not first.get("data_url"):
                return
            caption = await self._captioner.generate(ImageAttachment.from_dict(first))
            if caption:
                await repo.update_photo_caption(message_id, caption)
                await session.commit()


class InboxNoteHandler:
    def __init__(self, vault, broker) -> None:
        self._vault = vault
        self._broker = broker

    async def handle(self, task: TaskMessage) -> None:
        from vanessa.contracts.messages import InboxNoteReply
        from vanessa.knowledge.inbox import InboxNoteError, save_inbox_note

        payload = task.payload
        raw_attachment = payload.get("attachment_base64")
        try:
            path = await save_inbox_note(
                self._vault,
                text=str(payload.get("text") or ""),
                attachment_base64=(
                    str(raw_attachment) if raw_attachment else None
                ),
                attachment_suffix=str(payload.get("attachment_suffix") or ".jpg"),
            )
            reply = InboxNoteReply(
                correlation_id=task.correlation_id,
                ok=True,
                path=path,
            )
        except InboxNoteError as exc:
            reply = InboxNoteReply(
                correlation_id=task.correlation_id,
                ok=False,
                error=exc.code,
            )
        if task.reply_to and self._broker is not None:
            await self._broker.publish(task.reply_to, reply)


async def build_worker_handlers(broker=None) -> WorkerAssembly:
    """Assemble the real handlers + polling loops (worker process)."""
    from vanessa.config import settings
    from vanessa.infrastructure.db.session import async_session_factory
    from vanessa.infrastructure.runtime.vector_stores import (
        create_embedding_provider,
        create_knowledge_vector_store,
        create_message_vector_store,
    )
    from vanessa.knowledge.index import KnowledgeIndex
    from vanessa.knowledge.memory_planner import MemoryPlanner
    from vanessa.knowledge.memory_stage import MemoryStage
    from vanessa.knowledge.metrics.deterministic import DeterministicMetricsCalculator
    from vanessa.knowledge.metrics.pipeline import MetricsPipeline
    from vanessa.knowledge.metrics.planner import MetricsPlanner
    from vanessa.knowledge.metrics.store import MetricsStore
    from vanessa.knowledge.portraits import PortraitBuilder, PortraitPlanner
    from vanessa.knowledge.sweep import SweepAnalyzer
    from vanessa.knowledge.vault import KnowledgeVault
    from vanessa.knowledge.vector_index import KnowledgeVectorIndexer
    from vanessa.knowledge.writer import KnowledgeVaultWriter
    from vanessa.pipeline.llm.photo_captioner import PhotoCaptioner

    vault = KnowledgeVault()
    await vault.ensure_structure()
    try:
        from vanessa.knowledge.compaction import compact_all_person_cards

        await compact_all_person_cards(vault)
    except Exception:
        logger.exception("knowledge_compaction_failed at worker startup")
    index = KnowledgeIndex(vault)
    embeddings = create_embedding_provider()
    knowledge_vector_store = create_knowledge_vector_store()
    vector_store = create_message_vector_store()
    knowledge_vector_indexer = KnowledgeVectorIndexer(
        vault, embeddings, knowledge_vector_store
    )
    try:
        await knowledge_vector_indexer.index_all()
    except Exception:
        logger.exception("knowledge_vector_index_all_failed at worker startup")
    writer = KnowledgeVaultWriter(
        vault, index, vector_indexer=knowledge_vector_indexer
    )
    metrics_pipeline = MetricsPipeline(
        MetricsStore(vault, index),
        MetricsPlanner(),
        DeterministicMetricsCalculator(
            history_days=settings.knowledge_metrics_history_days
        ),
        enabled=settings.knowledge_metrics_enabled,
        cooldown_seconds=settings.knowledge_metrics_cooldown_seconds,
    )
    sweep = SweepAnalyzer(
        vault,
        MemoryPlanner(),
        writer,
        interval_messages=settings.knowledge_sweep_interval_messages,
        batch_size=settings.knowledge_sweep_batch_size,
        window_size=settings.knowledge_sweep_window_size,
        window_overlap=settings.knowledge_sweep_window_overlap,
        metrics=metrics_pipeline,
    )
    portrait = PortraitBuilder(vault, PortraitPlanner())

    index_handler = IndexMessageHandler(
        embeddings,
        vector_store,
        async_session_factory,
        max_retries=settings.indexing_max_retries,
    )
    memory = MemoryStage(
        writer,
        MemoryPlanner(),
        enabled=settings.knowledge_memory_enabled,
        cooldown_seconds=settings.knowledge_memory_cooldown_seconds,
        prefilter_enabled=settings.knowledge_memory_prefilter_enabled,
        prefilter_min_messages=settings.knowledge_memory_prefilter_min_messages,
        prefilter_min_content_chars=(
            settings.knowledge_memory_prefilter_min_content_chars
        ),
        prefilter_score_threshold=(
            settings.knowledge_memory_prefilter_score_threshold
        ),
    )
    return WorkerAssembly(
        handlers={
            TaskKind.INDEX_MESSAGE: index_handler,
            TaskKind.VECTOR_INDEX: index_handler,
            TaskKind.SWEEP: SweepHandler(sweep, async_session_factory),
            TaskKind.PORTRAIT: PortraitHandler(portrait),
            TaskKind.REINDEX_KNOWLEDGE: ReindexKnowledgeHandler(
                knowledge_vector_indexer
            ),
            TaskKind.MEMORY_EXTRACT: MemoryExtractHandler(memory),
            TaskKind.METRICS_SNAPSHOT: MetricsSnapshotHandler(
                metrics_pipeline, async_session_factory
            ),
            TaskKind.PHOTO_CAPTION: PhotoCaptionHandler(
                PhotoCaptioner(), async_session_factory
            ),
            TaskKind.INBOX_NOTE: InboxNoteHandler(vault, broker),
        },
        sweep=sweep,
        portrait=portrait,
    )
