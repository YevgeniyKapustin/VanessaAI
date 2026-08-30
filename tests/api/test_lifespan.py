from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.lifespan import lifespan
from services.agent.runtime.broker import BrokerRuntime

STORAGE = "services.agent.runtime.storage"
WARMUP = "services.agent.runtime.warmup"
KNOWLEDGE = "services.agent.runtime.knowledge"


def _mock_container(vector_store, embeddings) -> MagicMock:
    container = MagicMock()
    container.role.owns_knowledge_loops = False
    graph = container.graph
    graph.retrieval.indexes.messages = vector_store
    graph.retrieval.embeddings = embeddings
    graph.jobs.start = MagicMock()
    graph.jobs.shutdown = AsyncMock()
    graph.broker.close = AsyncMock()
    graph.knowledge.vault.ensure_structure = AsyncMock()
    graph.knowledge.vector_indexer.index_all = AsyncMock()
    return container


def _patch_knowledge_flags(monkeypatch) -> None:
    monkeypatch.setattr(f"{KNOWLEDGE}.settings.knowledge_sweep_enabled", False)
    monkeypatch.setattr(f"{KNOWLEDGE}.settings.knowledge_portrait_enabled", False)
    monkeypatch.setattr(
        "vanessa.knowledge.compaction.compact_all_person_cards",
        AsyncMock(),
    )


def _patch_broker_runtime(monkeypatch) -> None:
    monkeypatch.setattr(BrokerRuntime, "start", AsyncMock())


@pytest.mark.asyncio
async def test_lifespan_runs_startup_and_shutdown(monkeypatch):
    mock_conn = AsyncMock()
    mock_conn.run_sync = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.begin = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    mock_engine.dispose = AsyncMock()
    monkeypatch.setattr(f"{STORAGE}.engine", mock_engine)
    monkeypatch.setattr(f"{STORAGE}.settings.api_auto_create_schema", True)
    _patch_knowledge_flags(monkeypatch)
    _patch_broker_runtime(monkeypatch)

    vector_store = AsyncMock()
    vector_store.ensure_collection = AsyncMock()
    embeddings = AsyncMock()
    embeddings.embed = AsyncMock(return_value=[0.1])
    container = _mock_container(vector_store, embeddings)
    monkeypatch.setattr(f"{WARMUP}.preload_embedding_model", lambda: None)
    async with lifespan(container):
        vector_store.ensure_collection.assert_awaited_once()
        embeddings.embed.assert_awaited_once_with("warmup")

    mock_engine.dispose.assert_awaited_once()
    mock_conn.run_sync.assert_awaited_once()
    container.graph.jobs.shutdown.assert_awaited_once()
    container.graph.broker.close.assert_awaited_once()
