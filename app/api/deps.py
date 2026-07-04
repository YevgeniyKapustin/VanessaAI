from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.content import get_bot_name_aliases, get_trigger_keywords
from app.config.conversation_config import load_conversation_config
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
    IntentDetector,
    NoiseFilter,
    PlannerPrefilter,
    QdrantRelevanceChecker,
    RateLimiter,
    SessionWindowAnalyzer,
    TriggerKeywordChecker,
)
from app.llm.providers.claude import ClaudeLLMProvider
from app.rag.embeddings.embeddings import LocalEmbeddingProvider
from app.rag.search.hybrid_search import HybridSearchService
from app.rag.qdrant_client import QdrantVectorStore
from app.rag.query_rewriter import QueryRewriter
from app.services.orchestrator.conversation_orchestrator import ConversationOrchestrator
from app.services.humor_pipeline import HumorPipeline
from app.services.indexing.message_indexing import MessageIndexingService
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.stages import (
    ComposeStage,
    FinalizeStage,
    GateStage,
    RetrieveStage,
)
from app.services.turn_metrics import turn_metrics

_rate_limiter = RateLimiter(
    max_replies=settings.decision_rate_limit_per_minute,
    window_seconds=60,
)
_embedding_provider: EmbeddingProviderProtocol | None = None
_vector_store: VectorStoreProtocol | None = None
_intent_detector = IntentDetector(bot_names=get_bot_name_aliases())
_trigger_checker = TriggerKeywordChecker(keywords=get_trigger_keywords())
_conversation_config = load_conversation_config()
_session_analyzer = SessionWindowAnalyzer(
    window_size=_conversation_config.session_window_size,
    intent_detector=_intent_detector,
    trigger_checker=_trigger_checker,
)
_noise_filter = NoiseFilter()
_planner_prefilter = PlannerPrefilter(
    intent_detector=_intent_detector,
    trigger_checker=_trigger_checker,
    noise_filter=_noise_filter,
    post_reply_listen_count=_conversation_config.post_reply_listen_count,
    post_reply_listen_idle_seconds=_conversation_config.session_idle_seconds,
)


def create_embedding_provider() -> EmbeddingProviderProtocol:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = LocalEmbeddingProvider()
    return _embedding_provider


def create_vector_store() -> VectorStoreProtocol:
    global _vector_store
    if _vector_store is None:
        _vector_store = QdrantVectorStore()
    return _vector_store


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
    relevance = QdrantRelevanceChecker(
        embedding_provider=embeddings,
        vector_store=vector_store,
    )
    return DecisionEngine(
        intent_detector=_intent_detector,
        trigger_checker=_trigger_checker,
        relevance_checker=relevance,
        session_analyzer=_session_analyzer,
        rate_limiter=_rate_limiter,
        noise_filter=_noise_filter,
        relevance_threshold=settings.decision_relevance_threshold,
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


def create_query_rewriter() -> QueryRewriter:
    return QueryRewriter()


def get_query_rewriter() -> QueryRewriter:
    return create_query_rewriter()


def get_llm_provider() -> LLMProviderProtocol:
    return ClaudeLLMProvider()


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
    humor = HumorPipeline(hybrid_search, hybrid_search, config)
    gate = GateStage(
        query_rewriter,
        decision_engine,
        _planner_prefilter,
        config,
        metrics,
        messages,
        indexing,
    )
    retrieve = RetrieveStage(hybrid_search, humor, uow)
    compose = ComposeStage(llm)
    finalize = FinalizeStage(messages, indexing, decision_engine, config, metrics)
    return ConversationOrchestrator(
        messages=messages,
        users=users,
        config=config,
        gate=gate,
        retrieve=retrieve,
        compose=compose,
        finalize=finalize,
    )
