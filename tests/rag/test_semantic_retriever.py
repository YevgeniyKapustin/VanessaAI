import pytest

from app.knowledge.format import PEOPLE
from app.knowledge.index import KnowledgeIndex
from app.knowledge.retriever import KnowledgeRetriever
from app.knowledge.vault import KnowledgeVault


class FakeEmbeddings:
    def __init__(self) -> None:
        self.embedded: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.embedded.append(text)
        return [float(len(text))] * 4

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] * 4 for text in texts]


class FakeStore:
    def __init__(self, hits: list[dict]) -> None:
        self.hits = hits

    async def search(self, vector: list[float], limit: int = 30) -> list[dict]:
        return self.hits[:limit]


async def _seed_vault(tmp_path) -> tuple[KnowledgeVault, KnowledgeIndex]:
    vault = KnowledgeVault(str(tmp_path))
    await vault.write_note(
        "People/личь.md",
        {"type": "person", "id": "личь", "aliases": ["Личь"], "mood": "согласный"},
        "## Контекст жизни\n\n- 2026-08-26: Философ и сварщик.\n",
    )
    await vault.write_note(
        "Lore/events/2026-01-01-тест-ивент.md",
        {"type": "event", "id": "тест-ивент", "title": "тест ивент", "date": "2026-01-01"},
        "## Суть\n\n- 2026-01-01: Обсуждение игры.\n",
    )
    index = KnowledgeIndex(vault)
    await index.rebuild_folder(PEOPLE)
    return vault, index


@pytest.mark.asyncio
async def test_fetch_semantic_returns_vector_matches(tmp_path):
    vault, index = await _seed_vault(tmp_path)
    store = FakeStore(
        [
            {"path": "People/личь.md", "kind": "people", "title": "личь", "score": 0.9},
            {
                "path": "Lore/events/2026-01-01-тест-ивент.md",
                "kind": "lore",
                "title": "тест ивент",
                "score": 0.8,
            },
        ]
    )
    retriever = KnowledgeRetriever(
        vault,
        index,
        max_blocks=3,
        embeddings=FakeEmbeddings(),
        vector_store=store,
        vector_min_score=0.3,
    )

    blocks = await retriever.fetch_semantic("личь сварщик")

    paths = [block.path for block in blocks]
    assert "People/личь.md" in paths
    assert "Lore/events/2026-01-01-тест-ивент.md" in paths


@pytest.mark.asyncio
async def test_fetch_semantic_filters_by_kind(tmp_path):
    vault, index = await _seed_vault(tmp_path)
    store = FakeStore(
        [
            {"path": "People/личь.md", "kind": "people", "title": "личь", "score": 0.9},
            {
                "path": "Lore/events/2026-01-01-тест-ивент.md",
                "kind": "lore",
                "title": "тест ивент",
                "score": 0.8,
            },
        ]
    )
    retriever = KnowledgeRetriever(
        vault,
        index,
        max_blocks=3,
        embeddings=FakeEmbeddings(),
        vector_store=store,
        vector_min_score=0.3,
    )

    blocks = await retriever.fetch_semantic(
        "личь сварщик",
        knowledge_indexes=("lore",),
        knowledge_query="личь сварщик",
    )

    assert [block.path for block in blocks] == [
        "Lore/events/2026-01-01-тест-ивент.md"
    ]


@pytest.mark.asyncio
async def test_fetch_semantic_filters_below_min_score(tmp_path):
    vault, index = await _seed_vault(tmp_path)
    store = FakeStore(
        [
            {"path": "People/личь.md", "kind": "people", "title": "личь", "score": 0.1},
        ]
    )
    retriever = KnowledgeRetriever(
        vault,
        index,
        max_blocks=3,
        embeddings=FakeEmbeddings(),
        vector_store=store,
        vector_min_score=0.3,
    )

    blocks = await retriever.fetch_semantic("личь сварщик")

    assert blocks == []


@pytest.mark.asyncio
async def test_fetch_semantic_empty_query_returns_empty(tmp_path):
    vault, index = await _seed_vault(tmp_path)
    store = FakeStore([])
    retriever = KnowledgeRetriever(
        vault,
        index,
        max_blocks=3,
        embeddings=FakeEmbeddings(),
        vector_store=store,
    )

    assert await retriever.fetch_semantic("  ") == []


@pytest.mark.asyncio
async def test_fetch_semantic_falls_back_to_alias_fetch(tmp_path):
    vault, index = await _seed_vault(tmp_path)
    # No embeddings/vector store -> pure alias/token matching via fetch().
    retriever = KnowledgeRetriever(vault, index, max_blocks=3)

    blocks = await retriever.fetch_semantic(
        "личь",
        knowledge_indexes=("people",),
        knowledge_query="личь",
    )

    assert [block.path for block in blocks] == ["People/личь.md"]
