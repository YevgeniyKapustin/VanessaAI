from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.container import AppContainer, Persistence
from services.agent.deps import (
    get_incoming_turn_handler,
    get_turn_metrics,
    get_turn_session,
)
from vanessa.infrastructure.db.repository import MessageRepository, UserRepository
from vanessa.pipeline.decision import DecisionEngine
from vanessa.pipeline.orchestrator.conversation_orchestrator import (
    ConversationOrchestrator,
)
from vanessa.pipeline.rag.search.hybrid_search import HybridSearchService
from vanessa.pipeline.turn_metrics import TurnMetrics


def _request(container: AppContainer):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(container=container))
    )


def test_app_container_composes_factories() -> None:
    persistence = Persistence()
    search = MagicMock()
    indexing = MagicMock()
    graph = MagicMock()
    from services.agent.container import TurnWiring

    turns = TurnWiring(
        graph,
        persistence=persistence,
        search=search,
        indexing=indexing,
        decision_factory=MagicMock(),
        orchestrator=MagicMock(),
    )
    app = AppContainer(graph=graph, turns=turns)
    assert app.turns.persistence is persistence
    assert app.turns.search is search
    assert app.turns.indexing is indexing


def test_get_turn_metrics_returns_singleton():
    container = AppContainer()
    request = _request(container)
    first = get_turn_metrics(request)
    second = get_turn_metrics(request)
    assert isinstance(first, TurnMetrics)
    assert first is second
    first.record_turn(action="reply", reason="intent")
    assert first.snapshot().total == 1
    first.reset()
    assert first.snapshot().total == 0


def test_decision_engine_builds_from_graph():
    container = AppContainer()
    embeddings = container.graph.retrieval.embeddings
    vector_store = container.graph.retrieval.indexes.messages
    engine = container.turns.decision_factory.engine(embeddings, vector_store)
    assert isinstance(engine, DecisionEngine)


def test_hybrid_search_wires_dependencies():
    container = AppContainer()
    messages = MessageRepository.__new__(MessageRepository)
    embeddings = container.graph.retrieval.embeddings
    vector_store = container.graph.retrieval.indexes.messages
    service = container.turns.search.hybrid(messages, embeddings, vector_store)
    assert isinstance(service, HybridSearchService)


def test_query_rewriter():
    assert AppContainer().turns.search.query_rewriter() is not None


def test_embedding_provider_is_singleton():
    container = AppContainer()
    first = container.graph.retrieval.embeddings
    second = container.graph.retrieval.embeddings
    assert first is second


def test_repositories_from_persistence():
    persistence = Persistence()
    session = MagicMock()
    assert isinstance(persistence.messages(session), MessageRepository)
    assert isinstance(persistence.users(session), UserRepository)


@pytest.mark.asyncio
async def test_get_turn_session_commits_on_success():
    session = AsyncMock()
    agen = get_turn_session(session)
    yielded = await agen.__anext__()
    assert yielded is session
    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_turn_session_rolls_back_on_error():
    session = AsyncMock()
    agen = get_turn_session(session)
    await agen.__anext__()
    with pytest.raises(RuntimeError, match="boom"):
        await agen.athrow(RuntimeError("boom"))
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_incoming_turn_handler_builds_orchestrator():
    container = AppContainer()
    session = AsyncMock()
    handler = await get_incoming_turn_handler(_request(container), session)
    assert isinstance(handler, ConversationOrchestrator)
