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


@pytest.mark.asyncio
async def test_fetch_people_injects_portrait_not_raw_dossier(tmp_path):
    vault, index = await _seed_vault(tmp_path)
    note = await vault.read_note("People/личь.md")
    meta = dict(note.meta)
    meta["portrait"] = "Личь — философ и сварщик, держит ровное настроение."
    await vault.write_note(note.relative_path, meta, note.body)

    retriever = KnowledgeRetriever(vault, index, max_blocks=3, people_max_blocks=1)
    blocks = await retriever.fetch_semantic(
        "личь",
        knowledge_indexes=("people",),
        knowledge_query="личь",
    )

    assert len(blocks) == 1
    assert blocks[0].content == "Личь — философ и сварщик, держит ровное настроение."
    # The raw dossier is NOT dumped into the background context.
    assert "## Контекст жизни" not in blocks[0].content


@pytest.mark.asyncio
async def test_fetch_people_detail_pulls_raw_dossier(tmp_path):
    vault, index = await _seed_vault(tmp_path)
    note = await vault.read_note("People/личь.md")
    meta = dict(note.meta)
    meta["portrait"] = "Личь — философ и сварщик."
    await vault.write_note(note.relative_path, meta, note.body)

    retriever = KnowledgeRetriever(vault, index, max_blocks=3, people_max_blocks=1)
    blocks = await retriever.fetch_semantic(
        "личь",
        knowledge_indexes=("people",),
        knowledge_query="личь",
        people_detail=True,
    )

    assert len(blocks) == 1
    assert "Философ и сварщик" in blocks[0].content
    # A concrete-fact question pulls the raw dossier section.
    assert "## Контекст жизни" in blocks[0].content


@pytest.mark.asyncio
async def test_fetch_people_without_portrait_falls_back_to_raw(tmp_path):
    vault, index = await _seed_vault(tmp_path)
    retriever = KnowledgeRetriever(vault, index, max_blocks=3, people_max_blocks=1)

    blocks = await retriever.fetch_semantic(
        "личь",
        knowledge_indexes=("people",),
        knowledge_query="личь",
    )

    assert len(blocks) == 1
    assert "Философ и сварщик" in blocks[0].content


async def _add_kraber(tmp_path, vault, index) -> None:
    await vault.write_note(
        "People/крабер.md",
        {"type": "person", "id": "крабер", "aliases": ["Крабер"]},
        "## Контекст жизни\n\n- 2026-08-26: Любит пещеры.\n",
    )
    await index.rebuild_folder(PEOPLE)


@pytest.mark.asyncio
async def test_fetch_people_files_pulls_all_mentioned(tmp_path):
    vault, index = await _seed_vault(tmp_path)
    await _add_kraber(tmp_path, vault, index)

    retriever = KnowledgeRetriever(vault, index, max_blocks=3, people_max_blocks=3)
    blocks = await retriever.fetch_semantic(
        "крабер и личь",
        knowledge_indexes=("people",),
        knowledge_query="крабер личь",
        people_files=["People/крабер.md", "People/личь.md"],
    )

    paths = {block.path for block in blocks}
    assert "People/крабер.md" in paths
    assert "People/личь.md" in paths


@pytest.mark.asyncio
async def test_fetch_people_files_bounded_by_people_max_blocks(tmp_path):
    vault, index = await _seed_vault(tmp_path)
    await _add_kraber(tmp_path, vault, index)

    retriever = KnowledgeRetriever(vault, index, max_blocks=3, people_max_blocks=1)
    blocks = await retriever.fetch(
        knowledge_indexes=("people",),
        people_files=["People/крабер.md", "People/личь.md"],
    )

    assert len(blocks) == 1
    assert blocks[0].path == "People/крабер.md"


@pytest.mark.asyncio
async def test_fetch_people_files_portrait_by_default(tmp_path):
    vault, index = await _seed_vault(tmp_path)
    await _add_kraber(tmp_path, vault, index)
    for path, portrait in (
        ("People/личь.md", "Личь — философ и сварщик."),
        ("People/крабер.md", "Крабер — отшельник из пещеры."),
    ):
        note = await vault.read_note(path)
        meta = dict(note.meta)
        meta["portrait"] = portrait
        await vault.write_note(note.relative_path, meta, note.body)

    retriever = KnowledgeRetriever(vault, index, max_blocks=3, people_max_blocks=3)
    blocks = await retriever.fetch(
        knowledge_indexes=("people",),
        people_files=["People/крабер.md", "People/личь.md"],
    )

    contents = {block.content for block in blocks}
    assert "Крабер — отшельник из пещеры." in contents
    assert "Личь — философ и сварщик." in contents


@pytest.mark.asyncio
async def test_resolve_people_returns_mentioned_files(tmp_path):
    vault, index = await _seed_vault(tmp_path)
    await _add_kraber(tmp_path, vault, index)
    retriever = KnowledgeRetriever(vault, index)

    files = await retriever.resolve_people("что там у лича и крабера", [])
    assert set(files) == {"People/личь.md", "People/крабер.md"}
