from unittest.mock import AsyncMock

import pytest

from app.api.deps import (
    create_decision_engine,
    create_embedding_provider,
    create_hybrid_search,
    create_query_rewriter,
    create_vector_store,
    get_incoming_turn_handler,
    get_message_repository,
    get_turn_metrics,
    get_unit_of_work,
    get_user_repository,
)
from app.db.repository import MessageRepository, UserRepository
from app.db.uow import SqlAlchemyUnitOfWork
from app.decision import DecisionEngine
from app.rag.search.hybrid_search import HybridSearchService
from app.services.indexing.message_indexing import MessageIndexingService
from app.services.orchestrator.conversation_orchestrator import ConversationOrchestrator
from app.services.turn_metrics import TurnMetrics


def test_get_turn_metrics_returns_singleton():
    first = get_turn_metrics()
    second = get_turn_metrics()
    assert isinstance(first, TurnMetrics)
    assert first is second


def test_create_decision_engine_builds_engine():
    embeddings = create_embedding_provider()
    vector_store = create_vector_store()
    engine = create_decision_engine(embeddings, vector_store)
    assert isinstance(engine, DecisionEngine)


def test_create_hybrid_search_wires_dependencies():
    messages = MessageRepository.__new__(MessageRepository)
    embeddings = create_embedding_provider()
    vector_store = create_vector_store()
    service = create_hybrid_search(messages, embeddings, vector_store)
    assert isinstance(service, HybridSearchService)


def test_create_query_rewriter():
    assert create_query_rewriter() is not None


def test_embedding_provider_is_singleton():
    first = create_embedding_provider()
    second = create_embedding_provider()
    assert first is second


def test_vector_store_is_singleton():
    first = create_vector_store()
    second = create_vector_store()
    assert first is second


@pytest.mark.asyncio
async def test_get_message_repository():
    session = AsyncMock()
    repo = await get_message_repository(session)
    assert isinstance(repo, MessageRepository)


@pytest.mark.asyncio
async def test_get_user_repository():
    session = AsyncMock()
    repo = await get_user_repository(session)
    assert isinstance(repo, UserRepository)


@pytest.mark.asyncio
async def test_get_unit_of_work_commits_on_success():
    session = AsyncMock()
    agen = get_unit_of_work(session)
    uow = await agen.__anext__()
    assert isinstance(uow, SqlAlchemyUnitOfWork)
    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_unit_of_work_rolls_back_on_error():
    session = AsyncMock()
    agen = get_unit_of_work(session)
    await agen.__anext__()
    with pytest.raises(RuntimeError, match="boom"):
        await agen.athrow(RuntimeError("boom"))
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_incoming_turn_handler_builds_orchestrator():
    session = AsyncMock()
    messages = MessageRepository(session)
    users = UserRepository(session)
    embeddings = create_embedding_provider()
    vector_store = create_vector_store()
    hybrid = create_hybrid_search(messages, embeddings, vector_store)
    decision = create_decision_engine(embeddings, vector_store)
    from app.api.deps import (
        create_query_rewriter,
        get_llm_provider,
        get_turn_metrics,
    )

    indexing = MessageIndexingService(
        indexer=hybrid,
        messages=messages,
        session_factory=AsyncMock(),
        max_retries=0,
    )
    uow = SqlAlchemyUnitOfWork(session)
    handler = await get_incoming_turn_handler(
        messages=messages,
        users=users,
        hybrid_search=hybrid,
        indexing=indexing,
        llm=get_llm_provider(),
        decision_engine=decision,
        query_rewriter=create_query_rewriter(),
        uow=uow,
        metrics=get_turn_metrics(),
    )
    assert isinstance(handler, ConversationOrchestrator)
