from unittest.mock import AsyncMock, MagicMock

import pytest

from app.rag.qdrant_client import KnowledgeQdrantStore


def _make_client() -> MagicMock:
    client = MagicMock()
    collections = MagicMock()
    collections.collections = []
    client.get_collections = AsyncMock(return_value=collections)
    client.create_collection = AsyncMock()
    client.upsert = AsyncMock()
    client.delete_collection = AsyncMock()
    point = MagicMock()
    point.payload = {"path": "People/личь.md", "kind": "people", "title": "личь"}
    point.score = 0.88
    response = MagicMock()
    response.points = [point]
    client.query_points = AsyncMock(return_value=response)
    return client


def test_point_id_is_deterministic_and_path_scoped():
    a = KnowledgeQdrantStore.point_id("People/личь.md")
    b = KnowledgeQdrantStore.point_id("People/личь.md")
    c = KnowledgeQdrantStore.point_id("People/крабер.md")

    assert a == b
    assert a != c
    assert a.startswith("k:")


@pytest.mark.asyncio
async def test_upsert_note_returns_point_id():
    client = _make_client()
    store = KnowledgeQdrantStore(client=client, collection="knowledge", vector_size=3)

    pid = await store.upsert_note(
        "People/личь.md",
        "people",
        "личь",
        [0.1, 0.2, 0.3],
    )

    assert pid == KnowledgeQdrantStore.point_id("People/личь.md")
    client.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_notes_empty_returns_empty():
    client = _make_client()
    store = KnowledgeQdrantStore(client=client, collection="knowledge", vector_size=3)

    assert await store.upsert_notes([]) == []


@pytest.mark.asyncio
async def test_upsert_note_chunks_returns_distinct_point_ids():
    client = _make_client()
    store = KnowledgeQdrantStore(client=client, collection="knowledge", vector_size=3)

    ids = await store.upsert_note_chunks(
        "People/личь.md",
        "people",
        "личь",
        [(0, "фрагмент один"), (1, "фрагмент два")],
        [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
    )

    assert len(ids) == 2
    assert len(set(ids)) == 2
    assert all(pid.startswith("k:") for pid in ids)
    assert ids[0] == KnowledgeQdrantStore.chunk_point_id("People/личь.md", 0)
    assert ids[1] == KnowledgeQdrantStore.chunk_point_id("People/личь.md", 1)


@pytest.mark.asyncio
async def test_upsert_note_chunks_empty_returns_empty():
    client = _make_client()
    store = KnowledgeQdrantStore(client=client, collection="knowledge", vector_size=3)

    assert await store.upsert_note_chunks("x", "people", "x", [], []) == []


@pytest.mark.asyncio
async def test_chunk_point_id_is_deterministic():
    assert KnowledgeQdrantStore.chunk_point_id(
        "People/личь.md", 0
    ) == KnowledgeQdrantStore.chunk_point_id("People/личь.md", 0)
    assert KnowledgeQdrantStore.chunk_point_id(
        "People/личь.md", 0
    ) != KnowledgeQdrantStore.chunk_point_id("People/личь.md", 1)
    assert KnowledgeQdrantStore.chunk_point_id(
        "People/личь.md", 0
    ).startswith("k:")


@pytest.mark.asyncio
async def test_search_maps_hits():
    client = _make_client()
    store = KnowledgeQdrantStore(client=client, collection="knowledge", vector_size=3)

    hits = await store.search([0.1, 0.2, 0.3], limit=5)

    assert hits == [
        {"path": "People/личь.md", "kind": "people", "title": "личь", "score": 0.88}
    ]


@pytest.mark.asyncio
async def test_search_maps_chunk_hits_with_index():
    client = _make_client()
    chunk_point = MagicMock()
    chunk_point.payload = {
        "path": "People/личь.md",
        "kind": "people",
        "title": "личь",
        "chunk_index": 2,
    }
    chunk_point.score = 0.77
    response = MagicMock()
    response.points = [chunk_point]
    client.query_points = AsyncMock(return_value=response)
    store = KnowledgeQdrantStore(client=client, collection="knowledge", vector_size=3)

    hits = await store.search([0.1, 0.2, 0.3], limit=5)

    assert hits == [
        {
            "path": "People/личь.md",
            "kind": "people",
            "title": "личь",
            "chunk_index": 2,
            "score": 0.77,
        }
    ]


@pytest.mark.asyncio
async def test_reset_deletes_collection():
    client = _make_client()
    store = KnowledgeQdrantStore(client=client, collection="knowledge", vector_size=3)

    await store.reset()

    client.delete_collection.assert_awaited_once()
