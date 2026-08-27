from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.container import get_app_container
from app.config.settings import settings
from app.core.protocols import (
    ContextRetrieverProtocol,
    EmbeddingProviderProtocol,
    IncomingTurnHandlerProtocol,
    LLMProviderProtocol,
    MessageIndexerProtocol,
    MessageIndexingSchedulerProtocol,
    MessageRepositoryProtocol,
    TurnMetricsProtocol,
    TurnQueryProtocol,
    UnitOfWorkProtocol,
    UserRepositoryProtocol,
    VectorStoreProtocol,
)
from app.decision.protocols import DecisionEngineProtocol
from app.db.repository import MessageRepository, UserRepository
from app.db.session import async_session_factory, get_session
from app.db.uow import SqlAlchemyUnitOfWork
from app.decision import (
    DecisionEngine,
    QdrantRelevanceChecker,
)
from app.knowledge.index import KnowledgeIndex
from app.knowledge.memory_planner import MemoryPlanner
from app.knowledge.memory_stage import MemoryStage
from app.knowledge.metrics.deterministic import DeterministicMetricsCalculator
from app.knowledge.metrics.pipeline import MetricsPipeline
from app.knowledge.metrics.planner import MetricsPlanner
from app.knowledge.metrics.retriever import MetricsRetriever
from app.knowledge.metrics.store import MetricsStore
from app.knowledge.participants import ParticipantsDigest
from app.knowledge.retriever import KnowledgeRetriever
from app.knowledge.vault import KnowledgeVault
from app.knowledge.vector_index import KnowledgeVectorIndexer
from app.knowledge.writer import KnowledgeVaultWriter
from app.llm.humor.critic import HumorCritic
from app.llm.providers import create_llm_provider
from app.observability.eval import RagTriadEvaluator
from app.rag.search.hybrid_search import HybridSearchService
from app.rag.query_rewriter import QueryRewriter
from app.services.orchestrator.conversation_orchestrator import ConversationOrchestrator
from app.services.humor_pipeline import HumorPipeline
from app.services.indexing.message_indexing import MessageIndexingService
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.critique_stage import CritiqueStage
from app.services.pipeline.stages import (
    ComposeStage,
    FinalizeStage,
    GateStage,
    RetrieveStage,
)
from app.services.turn_metrics import turn_metrics


def create_embedding_provider() -> EmbeddingProviderProtocol:
    return get_app_container().embedding_provider


def create_vector_store() -> VectorStoreProtocol:
    return get_app_container().vector_store


def create_hybrid_search(
    messages: MessageRepositoryProtocol,
    embeddings: EmbeddingProviderProtocol,
    vector_store: VectorStoreProtocol,
) -> HybridSearchService:
    return HybridSearchService(
        message_repo=messages,
        embedding_provider=embeddings,
        vector_store=vector_store,
    )


def create_decision_engine(
    embeddings: EmbeddingProviderProtocol,
    vector_store: VectorStoreProtocol,
) -> DecisionEngineProtocol:
    container = get_app_container()
    relevance = QdrantRelevanceChecker(
        embedding_provider=embeddings,
        vector_store=vector_store,
    )
    return DecisionEngine(
        intent_detector=container.intent_detector,
        trigger_checker=container.trigger_checker,
        relevance_checker=relevance,
        session_analyzer=container.session_analyzer,
        rate_limiter=container.rate_limiter,
        noise_filter=container.noise_filter,
        relevance_threshold=settings.decision_relevance_threshold,
        reply_eligibility=container.reply_eligibility,
        block_consecutive_replies=container.block_consecutive_replies,
        ignore_registry=container.ignore_registry,
    )


async def get_unit_of_work(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[UnitOfWorkProtocol, None]:
    uow = SqlAlchemyUnitOfWork(session)
    try:
        yield uow
        await uow.commit()
    except Exception:
        await uow.rollback()
        raise


async def get_message_repository(
    session: AsyncSession = Depends(get_session),
) -> MessageRepository:
    return MessageRepository(session)


async def get_user_repository(
    session: AsyncSession = Depends(get_session),
) -> UserRepositoryProtocol:
    return UserRepository(session)


def get_embedding_provider() -> EmbeddingProviderProtocol:
    return create_embedding_provider()


def get_vector_store() -> VectorStoreProtocol:
    return create_vector_store()


def get_hybrid_search(
    messages: MessageRepository = Depends(get_message_repository),
    embeddings: EmbeddingProviderProtocol = Depends(get_embedding_provider),
    vector_store: VectorStoreProtocol = Depends(get_vector_store),
) -> HybridSearchService:
    return create_hybrid_search(messages, embeddings, vector_store)


_participants_digest: ParticipantsDigest | None = None


def get_participants_digest() -> ParticipantsDigest:
    """Process-wide participants digest (mtime-cached across requests)."""
    global _participants_digest
    if _participants_digest is None:
        vault = KnowledgeVault()
        _participants_digest = ParticipantsDigest(vault, KnowledgeIndex(vault))
    return _participants_digest


def create_query_rewriter() -> QueryRewriter:
    return QueryRewriter(participants_provider=get_participants_digest().build)


def get_query_rewriter() -> QueryRewriter:
    return create_query_rewriter()


def get_llm_provider() -> LLMProviderProtocol:
    return create_llm_provider()


def get_decision_engine(
    embeddings: EmbeddingProviderProtocol = Depends(get_embedding_provider),
    vector_store: VectorStoreProtocol = Depends(get_vector_store),
) -> DecisionEngineProtocol:
    return create_decision_engine(embeddings, vector_store)


def get_message_indexing(
    messages: MessageRepository = Depends(get_message_repository),
    hybrid_search: HybridSearchService = Depends(get_hybrid_search),
) -> MessageIndexingSchedulerProtocol:
    return MessageIndexingService(
        indexer=hybrid_search,
        messages=messages,
        session_factory=async_session_factory,
        max_retries=settings.indexing_max_retries,
        background=get_app_container().background,
    )


def get_turn_metrics() -> TurnMetricsProtocol:
    return turn_metrics


async def get_incoming_turn_handler(
    messages: MessageRepository = Depends(get_message_repository),
    users: UserRepositoryProtocol = Depends(get_user_repository),
    hybrid_search: HybridSearchService = Depends(get_hybrid_search),
    indexing: MessageIndexingSchedulerProtocol = Depends(get_message_indexing),
    llm: LLMProviderProtocol = Depends(get_llm_provider),
    decision_engine: DecisionEngineProtocol = Depends(get_decision_engine),
    query_rewriter: QueryRewriter = Depends(get_query_rewriter),
    uow: UnitOfWorkProtocol = Depends(get_unit_of_work),
    metrics: TurnMetricsProtocol = Depends(get_turn_metrics),
) -> IncomingTurnHandlerProtocol:
    config = OrchestratorConfig.from_settings()
    container = get_app_container()
    humor = HumorPipeline(hybrid_search, hybrid_search, config)
    knowledge_vault = KnowledgeVault()
    knowledge_index = KnowledgeIndex(knowledge_vault)
    metrics_retriever = MetricsRetriever(knowledge_vault, knowledge_index)
    knowledge_embeddings = container.embedding_provider
    knowledge_vector_store = container.knowledge_vector_store
    knowledge_vector_indexer = KnowledgeVectorIndexer(
        knowledge_vault,
        knowledge_embeddings,
        knowledge_vector_store,
    )
    gate = GateStage(
        query_rewriter,
        decision_engine,
        container.planner_prefilter,
        config,
        metrics,
        messages,
        indexing,
        container.ignore_registry,
        metrics_retriever=metrics_retriever,
        reaction_gate=container.reaction_gate,
    )
    knowledge = KnowledgeRetriever(
        knowledge_vault,
        knowledge_index,
        max_blocks=settings.knowledge_max_blocks,
        people_max_blocks=settings.knowledge_people_max_blocks,
        embeddings=knowledge_embeddings,
        vector_store=knowledge_vector_store,
    )
    memory = MemoryStage(
        KnowledgeVaultWriter(
            knowledge_vault,
            knowledge_index,
            vector_indexer=knowledge_vector_indexer,
        ),
        MemoryPlanner(),
        enabled=settings.knowledge_memory_enabled,
        cooldown_seconds=settings.knowledge_memory_cooldown_seconds,
    )
    metrics_pipeline = MetricsPipeline(
        MetricsStore(knowledge_vault, knowledge_index),
        MetricsPlanner(),
        DeterministicMetricsCalculator(
            history_days=settings.knowledge_metrics_history_days
        ),
        enabled=settings.knowledge_metrics_enabled,
        cooldown_seconds=settings.knowledge_metrics_cooldown_seconds,
    )
    retrieve = RetrieveStage(
        hybrid_search,
        humor,
        uow,
        knowledge=knowledge,
        meme_catalog=container.meme_catalog,
        meme_decider=container.meme_decider,
    )
    compose = ComposeStage(llm)
    critique = CritiqueStage(llm, HumorCritic(), config)
    finalize = FinalizeStage(
        messages,
        indexing,
        decision_engine,
        config,
        metrics,
        meme_decider=container.meme_decider,
    )
    return ConversationOrchestrator(
        messages=messages,
        users=users,
        config=config,
        gate=gate,
        retrieve=retrieve,
        compose=compose,
        critique=critique,
        finalize=finalize,
        memory=memory,
        metrics=metrics_pipeline,
        background=container.background,
        session_factory=async_session_factory,
        # RAG Triad LLM-as-judge evaluation (sampled, off by default).
        eval=RagTriadEvaluator(),
    )
