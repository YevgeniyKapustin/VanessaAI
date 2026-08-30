from __future__ import annotations

from vanessa.config import settings
from vanessa.infrastructure.db.session import async_session_factory
from vanessa.knowledge.index import KnowledgeIndex
from vanessa.knowledge.memory_planner import MemoryPlanner
from vanessa.knowledge.memory_stage import MemoryStage
from vanessa.knowledge.metrics.deterministic import DeterministicMetricsCalculator
from vanessa.knowledge.metrics.pipeline import MetricsPipeline
from vanessa.knowledge.metrics.planner import MetricsPlanner
from vanessa.knowledge.metrics.retriever import MetricsRetriever
from vanessa.knowledge.metrics.store import MetricsStore
from vanessa.knowledge.portraits import PortraitBuilder, PortraitWorker
from vanessa.knowledge.retriever import KnowledgeRetriever
from vanessa.knowledge.sweep import SweepAnalyzer, SweepWorker
from vanessa.knowledge.vault import KnowledgeVault
from vanessa.knowledge.vector_index import KnowledgeVectorIndexer
from vanessa.knowledge.writer import KnowledgeVaultWriter


class KnowledgeGraph:
    def __init__(
        self,
        retrieval,
        vault: KnowledgeVault | None = None,
        index: KnowledgeIndex | None = None,
        vector_indexer: KnowledgeVectorIndexer | None = None,
    ) -> None:
        self._retrieval = retrieval
        self.vault = vault or KnowledgeVault()
        self.index = index or KnowledgeIndex(self.vault)
        self.vector_indexer = vector_indexer or KnowledgeVectorIndexer(
            self.vault,
            retrieval.embeddings,
            retrieval.indexes.knowledge,
        )

    def vault_writer(self) -> KnowledgeVaultWriter:
        return KnowledgeVaultWriter(
            self.vault,
            self.index,
            vector_indexer=self.vector_indexer,
        )

    def metrics_retriever(self) -> MetricsRetriever:
        return MetricsRetriever(self.vault, self.index)

    def metrics_pipeline(
        self,
        *,
        cooldown_seconds: int | None = None,
    ) -> MetricsPipeline:
        extra = {}
        if cooldown_seconds is not None:
            extra["cooldown_seconds"] = cooldown_seconds
        return MetricsPipeline(
            MetricsStore(self.vault, self.index),
            MetricsPlanner(),
            DeterministicMetricsCalculator(
                history_days=settings.knowledge_metrics_history_days
            ),
            enabled=settings.knowledge_metrics_enabled,
            **extra,
        )

    def retriever(self) -> KnowledgeRetriever:
        return KnowledgeRetriever(
            self.vault,
            self.index,
            max_blocks=settings.knowledge_max_blocks,
            people_max_blocks=settings.knowledge_people_max_blocks,
            embeddings=self._retrieval.embeddings,
            vector_store=self._retrieval.indexes.knowledge,
        )

    def memory_stage(self) -> MemoryStage:
        return MemoryStage(
            self.vault_writer(),
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

    def sweep_analyzer(self) -> SweepAnalyzer:
        return SweepAnalyzer(
            self.vault,
            MemoryPlanner(),
            self.vault_writer(),
            interval_messages=settings.knowledge_sweep_interval_messages,
            batch_size=settings.knowledge_sweep_batch_size,
            window_size=settings.knowledge_sweep_window_size,
            window_overlap=settings.knowledge_sweep_window_overlap,
            metrics=self.metrics_pipeline(),
        )

    def sweep_worker(self, session_factory=None) -> SweepWorker:
        return SweepWorker(
            self.sweep_analyzer(),
            session_factory or async_session_factory,
            poll_seconds=settings.knowledge_sweep_poll_seconds,
        )

    def portrait_worker(self) -> PortraitWorker:
        return PortraitWorker(
            PortraitBuilder(self.vault),
            poll_seconds=settings.knowledge_portrait_poll_seconds,
        )
