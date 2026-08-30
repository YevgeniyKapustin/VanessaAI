from services.agent.container.engines import TurnEngines
from services.agent.container.graph import ProcessGraph
from vanessa.core.protocols import (
    IncomingTurnHandlerProtocol,
    MessageIndexingSchedulerProtocol,
    MessageRepositoryProtocol,
    TurnMetricsProtocol,
    UnitOfWorkProtocol,
    UserRepositoryProtocol,
)
from vanessa.infrastructure.db.session import async_session_factory
from vanessa.pipeline.humor_pipeline import HumorPipeline
from vanessa.pipeline.orchestrator.conversation_orchestrator import (
    ConversationOrchestrator,
)
from vanessa.pipeline.rag.search.hybrid_search import HybridSearchService
from vanessa.pipeline.stages import ComposeStage, FinalizeStage, GateStage, RetrieveStage


class OrchestratorFactory:
    def __init__(self, graph: ProcessGraph, turns) -> None:
        self._graph = graph
        self._turns = turns

    def build(
        self,
        messages: MessageRepositoryProtocol,
        users: UserRepositoryProtocol,
        hybrid_search: HybridSearchService,
        indexing: MessageIndexingSchedulerProtocol,
        uow: UnitOfWorkProtocol,
        metrics: TurnMetricsProtocol,
        engines: TurnEngines,
    ) -> IncomingTurnHandlerProtocol:
        graph = self._graph
        decision = graph.decision
        memes = graph.memes
        config = engines.config
        humor = HumorPipeline(hybrid_search, hybrid_search, config)
        gate = GateStage(
            engines.query_rewriter,
            engines.decision,
            decision.eligibility.prefilter,
            config,
            metrics,
            messages,
            indexing,
            decision.ignore_registry,
            metrics_retriever=engines.metrics_retriever,
            reaction_gate=decision.reaction_gate,
        )
        retrieve = RetrieveStage(
            hybrid_search,
            humor,
            uow,
            knowledge=engines.knowledge,
            meme_catalog=memes.catalog,
            meme_decider=memes.decider,
            web_search=engines.web_search,
        )
        compose = ComposeStage(
            engines.llm,
            refuse_enabled=config.compose_refuse_enabled,
            messages=messages,
        )
        finalize = FinalizeStage(
            messages,
            indexing,
            engines.decision,
            config,
            metrics,
            meme_decider=memes.decider,
        )
        return ConversationOrchestrator(
            messages=messages,
            users=users,
            config=config,
            gate=gate,
            retrieve=retrieve,
            compose=compose,
            finalize=finalize,
            memory=engines.memory,
            metrics=engines.metrics,
            background=graph.jobs.executor,
            session_factory=async_session_factory,
            eval=engines.eval,
            photo_captioner=engines.photo,
            dispatcher=self._turns.indexing.task_dispatcher(),
        )
