from unittest.mock import AsyncMock, MagicMock

import pytest

from app.rag.qdrant_client import QdrantVectorStore


def _make_client(*, collection_exists: bool = False) -> MagicMock:
    client = MagicMock()
    collection = MagicMock()
    collection.name = "messages"
    collections = MagicMock()
    collections.collections = [collection] if collection_exists else []
    client.get_collections = AsyncMock(return_value=collections)
    client.create_collection = AsyncMock()
    client.upsert = AsyncMock()
    point = MagicMock()
    point.payload = {"message_id": 42}
    point.score = 0.91
    response = MagicMock()
    response.points = [point]
    client.query_points = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_ensure_collection_creates_when_missing():
    client = _make_client(collection_exists=False)
    store = QdrantVectorStore(client=client, collection="messages", vector_size=3)
    await store.ensure_collection()
    client.create_collection.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_collection_skips_existing():
    client = _make_client(collection_exists=True)
    store = QdrantVectorStore(client=client, collection="messages", vector_size=3)
    await store.ensure_collection()
    client.create_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_message_returns_point_id():
    client = _make_client()
    store = QdrantVectorStore(client=client, collection="messages", vector_size=3)
    point_id = await store.upsert_message(
        1,
        "user",
        "hello",
        [0.1, 0.2, 0.3],
        point_id="fixed-id",
    )
    assert point_id == "fixed-id"
    client.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_batch_empty_returns_empty():
    client = _make_client()
    store = QdrantVectorStore(client=client, collection="messages", vector_size=3)
    assert await store.upsert_batch([]) == []


@pytest.mark.asyncio
async def test_search_maps_hits():
    client = _make_client()
    store = QdrantVectorStore(client=client, collection="messages", vector_size=3)
    hits = await store.search([0.1, 0.2, 0.3], limit=5)
    assert hits == [{"message_id": 42, "score": 0.91}]
