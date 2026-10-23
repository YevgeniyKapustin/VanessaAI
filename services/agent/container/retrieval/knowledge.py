from __future__ import annotations

from vanessa.config import settings
from vanessa.infrastructure.db.session import async_session_factory
from vanessa.knowledge.index import KnowledgeIndex
from vanessa.knowledge.memory import (
    KnowledgeVaultWriter,
    MemoryPlanner,
    MemoryStage,
    SweepAnalyzer,
    SweepWorker,
)
from vanessa.knowledge.metrics.deterministic import DeterministicMetricsCalculator
from vanessa.knowledge.metrics.pipeline import MetricsPipeline
from vanessa.knowledge.metrics.planner import MetricsPlanner
from vanessa.knowledge.metrics.retriever import MetricsRetriever
from vanessa.knowledge.metrics.store import MetricsStore
from vanessa.knowledge.pinned import PinnedNotes
from vanessa.knowledge.portraits import PortraitBuilder, PortraitWorker
from vanessa.knowledge.store.vault import KnowledgeVault


class KnowledgeGraph:
    def __init__(
        self,
        vault: KnowledgeVault | None = None,
        index: KnowledgeIndex | None = None,
    ) -> None:
        self.vault = vault or KnowledgeVault()
        self.index = index or KnowledgeIndex(self.vault)

    def vault_writer(self) -> KnowledgeVaultWriter:
        return KnowledgeVaultWriter(self.vault, self.index)

    def metrics_retriever(self) -> MetricsRetriever:
        return MetricsRetriever(self.vault, self.index)

    def pinned_notes(self) -> PinnedNotes | None:
        paths = settings.pinned_note_paths
        if not paths:
            return None
        return PinnedNotes(
            self.vault,
            paths,
            max_chars=settings.knowledge_pinned_max_chars,
        )

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
