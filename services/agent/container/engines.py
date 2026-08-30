from __future__ import annotations

from dataclasses import dataclass

from services.agent.container.decision_factory import DecisionFactory
from services.agent.container.graph import ProcessGraph
from services.agent.container.role import ProcessRole
from services.agent.container.search import Search
from vanessa.config.settings import settings
from vanessa.core.protocols import LLMProviderProtocol
from vanessa.infrastructure.observability.eval import RagTriadEvaluator
from vanessa.infrastructure.websearch.factory import create_web_search
from vanessa.infrastructure.websearch.protocols import WebSearchService
from vanessa.knowledge.memory_stage import MemoryStage
from vanessa.knowledge.metrics.pipeline import MetricsPipeline
from vanessa.knowledge.metrics.retriever import MetricsRetriever
from vanessa.knowledge.retriever import KnowledgeRetriever
from vanessa.pipeline.decision.protocols import DecisionEngineProtocol
from vanessa.pipeline.llm.photo_captioner import PhotoCaptioner
from vanessa.pipeline.llm.providers import create_llm_provider
from vanessa.pipeline.orchestrator.orchestrator_config import OrchestratorConfig
from vanessa.pipeline.rag.query_rewriter import QueryRewriter


@dataclass(frozen=True)
class TurnEngines:
    llm: LLMProviderProtocol
    web_search: WebSearchService | None
    query_rewriter: QueryRewriter
    decision: DecisionEngineProtocol
    memory: MemoryStage | None
    metrics: MetricsPipeline | None
    photo: PhotoCaptioner | None
    eval: RagTriadEvaluator
    config: OrchestratorConfig
    knowledge: KnowledgeRetriever
    metrics_retriever: MetricsRetriever

    @classmethod
    def build(
        cls,
        graph: ProcessGraph,
        role: ProcessRole,
        search: Search,
        decision_factory: DecisionFactory,
    ) -> TurnEngines:
        retrieval = graph.retrieval
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
            query_rewriter=search.query_rewriter(),
            decision=decision_factory.engine(
                retrieval.embeddings,
                retrieval.indexes.messages,
            ),
            memory=knowledge.memory_stage() if inline else None,
            metrics=metrics,
            photo=PhotoCaptioner() if inline else None,
            eval=RagTriadEvaluator(),
            config=OrchestratorConfig.from_settings(),
            knowledge=knowledge.retriever(),
            metrics_retriever=knowledge.metrics_retriever(),
        )
