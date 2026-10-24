from __future__ import annotations

from services.agent.container.graph import ProcessGraph
from services.agent.container.turns.engines import TurnEngines
from vanessa.core.protocols import (
    IncomingTurnHandlerProtocol,
    MessageRepositoryProtocol,
    TurnMetricsProtocol,
    UnitOfWorkProtocol,
    UserRepositoryProtocol,
)
from vanessa.infrastructure.db.session import async_session_factory
from vanessa.pipeline.orchestrator.conversation_orchestrator import (
    ConversationOrchestrator,
)
from vanessa.pipeline.stages import (
    ComposeStage,
    FinalizeStage,
    GateStage,
    RetrieveStage,
)
from vanessa.pipeline.vision.scene import SceneStage


class OrchestratorFactory:
    def __init__(self, graph: ProcessGraph) -> None:
        self._graph = graph

    def build(
        self,
        messages: MessageRepositoryProtocol,
        users: UserRepositoryProtocol,
        uow: UnitOfWorkProtocol,
        metrics: TurnMetricsProtocol,
        engines: TurnEngines,
    ) -> IncomingTurnHandlerProtocol:
        graph = self._graph
        dispatcher = graph.broker.task_dispatcher()
        decision = graph.decision
        memes = graph.memes
        config = engines.config
        gate = GateStage(
            engines.query_rewriter,
            engines.decision,
            decision.eligibility.prefilter,
            config,
            metrics,
            messages,
            decision.ignore_registry,
            metrics_retriever=engines.metrics_retriever,
            reaction_gate=decision.reaction_gate,
            bot_budget=decision.bot_budget,
        )
        retrieve = RetrieveStage(
            uow,
            meme_catalog=memes.catalog,
            meme_decider=memes.decider,
            web_search=engines.web_search,
            hermes=engines.hermes,
            dispatcher=dispatcher,
            reminders=engines.reminders,
            pinned_notes=engines.pinned_notes,
        )
        compose = ComposeStage(
            engines.llm,
            refuse_enabled=config.compose_refuse_enabled,
            messages=messages,
        )
        finalize = FinalizeStage(
            messages,
            engines.decision,
            metrics,
            meme_decider=memes.decider,
            bot_budget=decision.bot_budget,
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
            dispatcher=dispatcher,
            scene=SceneStage(engines.scene_describer),
        )
