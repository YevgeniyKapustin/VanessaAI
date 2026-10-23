from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.container import AppContainer, Persistence, TurnWiring
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
from vanessa.pipeline.turn_metrics import TurnMetrics


def _request(container: AppContainer):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(container=container))
    )


def test_app_container_composes_factories() -> None:
    persistence = Persistence()
    search = MagicMock()
    graph = MagicMock()
    turns = TurnWiring(
        graph,
        persistence=persistence,
        search=search,
        decision_factory=MagicMock(),
        orchestrator=MagicMock(),
    )
    app = AppContainer(graph=graph, turns=turns)
    assert app.turns.persistence is persistence
    assert app.turns.search is search


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
    engine = container.turns.decision_factory.engine()
    assert isinstance(engine, DecisionEngine)


def test_query_rewriter():
    assert AppContainer().turns.search.query_rewriter() is not None


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
