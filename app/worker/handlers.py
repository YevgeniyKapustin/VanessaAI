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

from app.contracts.messages import TaskKind, TaskMessage

logger = logging.getLogger(__name__)


@dataclass
class WorkerAssembly:
    """The fully-built worker components (handlers + polling loops)."""

    handlers: dict[TaskKind, "WorkerTaskHandler"]
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
                from app.db.repository import MessageRepository

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
        from app.core.messages import RAG_SOURCE_ROLE

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
            from app.db.repository import MessageRepository

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


async def build_worker_handlers() -> WorkerAssembly:
    """Assemble the real handlers + polling loops (worker process)."""
    from app.api.container import get_app_container
    from app.config import settings
    from app.db.session import async_session_factory
    from app.knowledge.index import KnowledgeIndex
    from app.knowledge.memory_planner import MemoryPlanner
    from app.knowledge.metrics.deterministic import DeterministicMetricsCalculator
    from app.knowledge.metrics.pipeline import MetricsPipeline
    from app.knowledge.metrics.planner import MetricsPlanner
    from app.knowledge.metrics.store import MetricsStore
    from app.knowledge.portraits import PortraitBuilder, PortraitPlanner
    from app.knowledge.sweep import SweepAnalyzer
    from app.knowledge.vault import KnowledgeVault
    from app.knowledge.vector_index import KnowledgeVectorIndexer
    from app.knowledge.writer import KnowledgeVaultWriter

    vault = KnowledgeVault()
    await vault.ensure_structure()
    index = KnowledgeIndex(vault)
    container = get_app_container()
    embeddings = container.embedding_provider
    knowledge_vector_store = container.knowledge_vector_store
    knowledge_vector_indexer = KnowledgeVectorIndexer(
        vault, embeddings, knowledge_vector_store
    )
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
        container.embedding_provider,
        container.vector_store,
        async_session_factory,
        max_retries=settings.indexing_max_retries,
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
        },
        sweep=sweep,
        portrait=portrait,
    )
