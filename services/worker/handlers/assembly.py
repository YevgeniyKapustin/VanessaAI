"""Compose worker handlers and polling collaborators (process DI root)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from services.worker.handlers.inbox import InboxNoteHandler
from services.worker.handlers.index import IndexMessageHandler
from services.worker.handlers.knowledge import (
    MemoryExtractHandler,
    MetricsSnapshotHandler,
    PortraitHandler,
    ReindexKnowledgeHandler,
    SweepHandler,
)
from services.worker.handlers.photo import PhotoCaptionHandler
from vanessa.config import settings
from vanessa.contracts.messages import TaskKind, TaskMessage
from vanessa.infrastructure.db.session import async_session_factory
from vanessa.infrastructure.runtime.vector_stores import (
    create_embedding_provider,
    create_knowledge_vector_store,
    create_message_vector_store,
)
from vanessa.knowledge.index import KnowledgeIndex
from vanessa.knowledge.memory import (
    KnowledgeVaultWriter,
    MemoryPlanner,
    MemoryStage,
    SweepAnalyzer,
    compaction,
)
from vanessa.knowledge.metrics.deterministic import DeterministicMetricsCalculator
from vanessa.knowledge.metrics.pipeline import MetricsPipeline
from vanessa.knowledge.metrics.planner import MetricsPlanner
from vanessa.knowledge.metrics.store import MetricsStore
from vanessa.knowledge.portraits import PortraitBuilder, PortraitPlanner
from vanessa.knowledge.store.vault import KnowledgeVault
from vanessa.knowledge.vectors import KnowledgeVectorIndexer
from vanessa.pipeline.llm.photo_captioner import PhotoCaptioner

logger = logging.getLogger(__name__)


@dataclass
class WorkerAssembly:
    """The fully-built worker components (handlers + polling loops)."""

    handlers: dict[TaskKind, WorkerTaskHandler]
    sweep: Any | None = None
    portrait: Any | None = None


class WorkerTaskHandler(Protocol):
    async def handle(self, task: TaskMessage) -> None: ...


async def build_worker_handlers(broker=None) -> WorkerAssembly:
    """Assemble the real handlers + polling loops (worker process)."""
    vault = KnowledgeVault()
    await vault.ensure_structure()
    try:
        await compaction.compact_all_person_cards(vault)
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
