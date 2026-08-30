from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.agent_core.container import get_app_container
from vanessa.config.settings import settings
from vanessa.core.protocols import (
    EmbeddingProviderProtocol,
    IncomingTurnHandlerProtocol,
    LLMProviderProtocol,
    MessageIndexingSchedulerProtocol,
    MessageRepositoryProtocol,
    TurnMetricsProtocol,
    UnitOfWorkProtocol,
    UserRepositoryProtocol,
    VectorStoreProtocol,
)
from vanessa.pipeline.decision.protocols import DecisionEngineProtocol
from vanessa.infrastructure.db.repository import MessageRepository, UserRepository
from vanessa.infrastructure.db.session import async_session_factory, get_session
from vanessa.infrastructure.db.uow import SqlAlchemyUnitOfWork
from vanessa.pipeline.decision import (
    DecisionEngine,
    QdrantRelevanceChecker,
)
from vanessa.knowledge.index import KnowledgeIndex
from vanessa.knowledge.memory_planner import MemoryPlanner
from vanessa.knowledge.memory_stage import MemoryStage
from vanessa.knowledge.metrics.deterministic import DeterministicMetricsCalculator
from vanessa.knowledge.metrics.pipeline import MetricsPipeline
from vanessa.knowledge.metrics.planner import MetricsPlanner
from vanessa.knowledge.metrics.retriever import MetricsRetriever
from vanessa.knowledge.metrics.store import MetricsStore
from vanessa.knowledge.participants import ParticipantsDigest
from vanessa.knowledge.retriever import KnowledgeRetriever
from vanessa.knowledge.vault import KnowledgeVault
from vanessa.knowledge.vector_index import KnowledgeVectorIndexer
from vanessa.knowledge.writer import KnowledgeVaultWriter
from vanessa.pipeline.llm.photo_captioner import PhotoCaptioner
from vanessa.pipeline.llm.providers import create_llm_provider
from vanessa.infrastructure.observability.eval import RagTriadEvaluator
from vanessa.pipeline.rag.search.hybrid_search import HybridSearchService
from vanessa.pipeline.rag.query_rewriter import QueryRewriter
from vanessa.pipeline.orchestrator.conversation_orchestrator import ConversationOrchestrator
from vanessa.pipeline.humor_pipeline import HumorPipeline
from vanessa.pipeline.indexing.message_indexing import MessageIndexingService
from vanessa.pipeline.orchestrator.orchestrator_config import OrchestratorConfig
from vanessa.pipeline.stages import (
    ComposeStage,
    FinalizeStage,
    GateStage,
    RetrieveStage,
)
from vanessa.pipeline.turn_metrics import turn_metrics
from vanessa.infrastructure.websearch.factory import create_web_search
from vanessa.infrastructure.websearch.protocols import WebSearchService


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


def get_web_search() -> WebSearchService | None:
    """Configured live web-search provider, or None when the skill is off."""
    return create_web_search()


def get_decision_engine(
    embeddings: EmbeddingProviderProtocol = Depends(get_embedding_provider),
    vector_store: VectorStoreProtocol = Depends(get_vector_store),
) -> DecisionEngineProtocol:
    return create_decision_engine(embeddings, vector_store)


_task_dispatcher = None


def get_task_dispatcher():
    """Lazy singleton broker task dispatcher (worker mode) shared across requests.

    Created only when ``settings.worker_enabled`` — the heavy embedding work is
    then handed to the dedicated worker container via the broker instead of the
    in-process executor.
    """
    global _task_dispatcher
    if _task_dispatcher is None and settings.worker_enabled:
        from vanessa.infrastructure.broker.redis_streams import RedisStreamBroker
        from vanessa.infrastructure.broker.streams import BrokerStreams
        from vanessa.infrastructure.broker.dispatcher import BrokerTaskDispatcher

        streams = BrokerStreams.from_settings(settings)
        _task_dispatcher = BrokerTaskDispatcher(
            RedisStreamBroker(
                settings.broker_redis_url,
                stream_maxlen=settings.broker_stream_maxlen,
                dlq_enabled=settings.broker_dlq_enabled,
            ),
            tasks_stream=streams.tasks,
        )
    return _task_dispatcher


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
        dispatcher=get_task_dispatcher(),
    )


def get_turn_metrics() -> TurnMetricsProtocol:
    return turn_metrics


def build_orchestrator(
    messages: MessageRepositoryProtocol,
    users: UserRepositoryProtocol,
    hybrid_search: HybridSearchService,
    indexing: MessageIndexingSchedulerProtocol,
    llm: LLMProviderProtocol,
    decision_engine: DecisionEngineProtocol,
    query_rewriter: QueryRewriter,
    uow: UnitOfWorkProtocol,
    metrics: TurnMetricsProtocol,
    web_search: WebSearchService | None,
) -> IncomingTurnHandlerProtocol:
    """Assemble the Gate → Retrieve → Compose → Finalize pipeline.

    Shared by the HTTP request dependency (``get_incoming_turn_handler``) and
    the broker turn worker, so both transports run the identical pipeline.
    """
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
        prefilter_enabled=settings.knowledge_memory_prefilter_enabled,
        prefilter_min_messages=settings.knowledge_memory_prefilter_min_messages,
        prefilter_min_content_chars=(
            settings.knowledge_memory_prefilter_min_content_chars
        ),
        prefilter_score_threshold=(
            settings.knowledge_memory_prefilter_score_threshold
        ),
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
        web_search=web_search,
    )
    compose = ComposeStage(
        llm,
        refuse_enabled=config.compose_refuse_enabled,
        # Meaning-driven photo-album search (find photos "по смыслу" of the
        # message, not by the literal words the user typed).
        messages=messages,
    )
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
        finalize=finalize,
        memory=None if settings.worker_enabled else memory,
        metrics=None if settings.worker_enabled else metrics_pipeline,
        background=container.background,
        session_factory=async_session_factory,
        eval=RagTriadEvaluator(),
        photo_captioner=None if settings.worker_enabled else PhotoCaptioner(),
        dispatcher=get_task_dispatcher() if settings.worker_enabled else None,
    )


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
    web_search: WebSearchService | None = Depends(get_web_search),
) -> IncomingTurnHandlerProtocol:
    return build_orchestrator(
        messages,
        users,
        hybrid_search,
        indexing,
        llm,
        decision_engine,
        query_rewriter,
        uow,
        metrics,
        web_search,
    )
