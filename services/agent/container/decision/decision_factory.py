from services.agent.container.graph import ProcessGraph
from vanessa.config.settings import settings
from vanessa.core.protocols import EmbeddingProviderProtocol, VectorStoreProtocol
from vanessa.pipeline.decision import DecisionEngine, QdrantRelevanceChecker
from vanessa.pipeline.decision.protocols import DecisionEngineProtocol


class DecisionFactory:
    def __init__(self, graph: ProcessGraph) -> None:
        self._graph = graph

    def engine(
        self,
        embeddings: EmbeddingProviderProtocol,
        vector_store: VectorStoreProtocol,
    ) -> DecisionEngineProtocol:
        decision = self._graph.decision
        signals = decision.signals
        eligibility = decision.eligibility
        relevance = QdrantRelevanceChecker(
            embedding_provider=embeddings,
            vector_store=vector_store,
        )
        return DecisionEngine(
            intent_detector=signals.intent,
            trigger_checker=signals.triggers,
            relevance_checker=relevance,
            session_analyzer=eligibility.session,
            rate_limiter=decision.rate_limiter,
            noise_filter=signals.noise,
            relevance_threshold=settings.decision_relevance_threshold,
            reply_eligibility=eligibility.reply,
            block_consecutive_replies=eligibility.block_consecutive_replies,
            ignore_registry=decision.ignore_registry,
        )
