from __future__ import annotations

from dataclasses import dataclass

from services.agent.container.decision.decision_factory import DecisionFactory
from services.agent.container.graph import ProcessGraph
from services.agent.container.role import ProcessRole
from services.agent.container.turns.search import Search
from vanessa.config.settings import settings
from vanessa.core.protocols import (
    HermesHealthProtocol,
    LLMProviderProtocol,
    PinnedNotesProtocol,
    ReminderStoreProtocol,
    SceneDescriberProtocol,
)
from vanessa.infrastructure.db.reminder_repository import create_reminder_store
from vanessa.infrastructure.hermes import create_hermes_client
from vanessa.infrastructure.observability.eval import RagTriadEvaluator
from vanessa.infrastructure.websearch.factory import create_web_search
from vanessa.infrastructure.websearch.protocols import WebSearchService
from vanessa.knowledge.memory import MemoryStage
from vanessa.knowledge.metrics.pipeline import MetricsPipeline
from vanessa.knowledge.metrics.retriever import MetricsRetriever
from vanessa.pipeline.decision.protocols import DecisionEngineProtocol
from vanessa.pipeline.llm.photo_captioner import PhotoCaptioner
from vanessa.pipeline.llm.planner.turn_planner import TurnPlanner
from vanessa.pipeline.llm.providers import create_llm_provider
from vanessa.pipeline.orchestrator.orchestrator_config import OrchestratorConfig
from vanessa.pipeline.vision.describer import SceneDescriber


@dataclass(frozen=True)
class TurnEngines:
    llm: LLMProviderProtocol
    web_search: WebSearchService | None
    hermes: HermesHealthProtocol | None
    query_rewriter: TurnPlanner
    decision: DecisionEngineProtocol
    memory: MemoryStage | None
    metrics: MetricsPipeline | None
    photo: PhotoCaptioner | None
    eval: RagTriadEvaluator
    config: OrchestratorConfig
    metrics_retriever: MetricsRetriever
    scene_describer: SceneDescriberProtocol
    # Posts Vanessa schedules for herself; None when the skill is off.
    reminders: ReminderStoreProtocol | None = None
    # Vault notes in every compose prompt; None when none are configured.
    pinned_notes: PinnedNotesProtocol | None = None

    @classmethod
    def build(
        cls,
        graph: ProcessGraph,
        role: ProcessRole,
        search: Search,
        decision_factory: DecisionFactory,
    ) -> TurnEngines:
        knowledge = graph.knowledge
        inline = role.inline_turn_effects
        metrics = None
        if inline:
            metrics = knowledge.metrics_pipeline(
                cooldown_seconds=settings.knowledge_metrics_cooldown_seconds,
            )
        return cls(
            llm=create_llm_provider(),
            web_search=create_web_search(),
            hermes=create_hermes_client(settings),
            query_rewriter=search.query_rewriter(),
            decision=decision_factory.engine(),
            memory=knowledge.memory_stage() if inline else None,
            metrics=metrics,
            photo=PhotoCaptioner() if inline else None,
            eval=RagTriadEvaluator(),
            config=OrchestratorConfig.from_settings(),
            metrics_retriever=knowledge.metrics_retriever(),
            scene_describer=SceneDescriber(),
            reminders=create_reminder_store(settings),
            pinned_notes=knowledge.pinned_notes(),
        )
