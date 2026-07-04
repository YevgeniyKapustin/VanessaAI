import pytest

from app.decision.detectors.relevance import QdrantRelevanceChecker


class FakeEmbeddings:
    async def embed(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class FakeVectorStore:
    def __init__(self, hits: list[dict] | None = None) -> None:
        self._hits = hits or []
        self.last_vector: list[float] | None = None

    async def search(self, vector: list[float], limit: int = 30) -> list[dict]:
        self.last_vector = vector
        return self._hits


@pytest.mark.asyncio
async def test_relevance_returns_zero_for_empty_text():
    checker = QdrantRelevanceChecker(FakeEmbeddings(), FakeVectorStore())
    assert await checker.score("   ", search_text="") == 0.0


@pytest.mark.asyncio
async def test_relevance_uses_search_text_and_embedding():
    store = FakeVectorStore([{"message_id": 1, "score": 0.82}])
    checker = QdrantRelevanceChecker(FakeEmbeddings(), store)
    score = await checker.score("ignored", search_text="тик так")
    assert score == pytest.approx(0.82)
    assert store.last_vector == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_relevance_uses_provided_vector():
    store = FakeVectorStore([{"message_id": 2, "score": 0.5}])
    checker = QdrantRelevanceChecker(FakeEmbeddings(), store)
    vector = [0.9, 0.1]
    score = await checker.score("text", query_vector=vector)
    assert score == 0.5
    assert store.last_vector == vector


@pytest.mark.asyncio
async def test_relevance_returns_zero_without_hits():
    checker = QdrantRelevanceChecker(FakeEmbeddings(), FakeVectorStore())
    assert await checker.score("hello") == 0.0
