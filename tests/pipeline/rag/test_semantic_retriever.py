import pytest

from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.index import KnowledgeIndex
from vanessa.knowledge.retriever import KnowledgeRetriever
from vanessa.knowledge.vault import KnowledgeVault


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


@pytest.mark.asyncio
async def test_fetch_semantic_people_detail_returns_top_chunks(tmp_path):
    """A detail query about a person returns several dossier blocks, ranked by
    embedding score — not a single short portrait."""
    vault, index = await _seed_vault(tmp_path)
    long_body = (
        "## Контекст жизни\n\n"
        "- 2026-08-26: Устроился сварщиком в Тик Так.\n"
        "- 2026-08-27: Любит пещеры и философию.\n"
        "- 2026-08-28: Переехал в Грузию.\n"
        "- 2026-08-29: Занимается закупкой долларов.\n"
        "- 2026-08-30: Ходит в походы по выходным.\n"
        "- 2026-08-31: Изучает итальянский язык.\n"
        "- 2026-09-01: Завёл кота по имени Бублик.\n"
        "- 2026-09-02: Пошёл на курсы бармена.\n"
        "- 2026-09-03: Планирует отпуск в Тбилиси.\n"
        "- 2026-09-04: Начал бегать по утрам.\n"
    )
    await vault.write_note(
        "People/личь.md",
        {"type": "person", "id": "личь", "aliases": ["Личь"]},
        long_body,
    )
    store = FakeStore(
        [
            {"path": "People/личь.md", "kind": "people", "title": "личь", "score": 0.9,
             "chunk_index": 0},
            {"path": "People/личь.md", "kind": "people", "title": "личь", "score": 0.85,
             "chunk_index": 1},
            {"path": "People/личь.md", "kind": "people", "title": "личь", "score": 0.8,
             "chunk_index": 2},
            {"path": "People/личь.md", "kind": "people", "title": "личь", "score": 0.7,
             "chunk_index": 3},
            {"path": "People/личь.md", "kind": "people", "title": "личь", "score": 0.6,
             "chunk_index": 4},
        ]
    )
    retriever = KnowledgeRetriever(
        vault,
        index,
        max_blocks=3,
        people_detail_blocks=5,
        people_chunk_chars=120,
        embeddings=FakeEmbeddings(),
        vector_store=store,
        vector_min_score=0.3,
    )

    blocks = await retriever.fetch_semantic(
        "личь доллары",
        knowledge_indexes=("people",),
        knowledge_query="личь доллары",
        people_detail=True,
    )

    assert len(blocks) == 5
    contents = [block.content for block in blocks]
    assert any("долларов" in content for content in contents)
    # Chunk blocks keep a fragment label and a chunk index for dedup.
    assert all(block.chunk_index is not None for block in blocks)
    assert blocks[0].title.startswith("личь")


@pytest.mark.asyncio
async def test_fetch_semantic_people_detail_dedupes_chunks(tmp_path):
    """Vector chunk hits for the same dossier don't duplicate after dedup."""
    vault, index = await _seed_vault(tmp_path)
    long_body = "\n".join(
        f"- 2026-08-{day:02d}: Факт номер {day} про лича." for day in range(1, 20)
    )
    await vault.write_note(
        "People/личь.md",
        {"type": "person", "id": "личь", "aliases": ["Личь"]},
        long_body,
    )
    store = FakeStore(
        [
            {"path": "People/личь.md", "kind": "people", "title": "личь", "score": 0.9,
             "chunk_index": 0},
            {"path": "People/личь.md", "kind": "people", "title": "личь", "score": 0.9,
             "chunk_index": 0},
            {"path": "People/личь.md", "kind": "people", "title": "личь", "score": 0.8,
             "chunk_index": 1},
        ]
    )
    retriever = KnowledgeRetriever(
        vault,
        index,
        max_blocks=3,
        people_detail_blocks=5,
        people_chunk_chars=120,
        embeddings=FakeEmbeddings(),
        vector_store=store,
        vector_min_score=0.3,
    )

    blocks = await retriever.fetch_semantic(
        "личь",
        knowledge_indexes=("people",),
        knowledge_query="личь",
        people_detail=True,
    )

    chunk_keys = [block.chunk_index for block in blocks]
    assert 0 in chunk_keys
    assert 1 in chunk_keys
    # The duplicate chunk_index 0 hit is collapsed to a single block.
    assert len([key for key in chunk_keys if key == 0]) == 1


async def _add_veronica(tmp_path, vault, index) -> None:
    await vault.write_note(
        "People/вероника.md",
        {
            "type": "person",
            "id": "вероника",
            "aliases": ["Вероника"],
            "portrait": "Вероника — 19-летняя студентка и скрипачка.",
        },
        "## Контекст жизни\n\n- 2026-08-26: Учится на скрипке.\n",
    )
    await index.rebuild_folder(PEOPLE)


async def _add_vanessa_self(tmp_path, vault, index) -> None:
    await vault.write_note(
        "People/ванесса.md",
        {
            "type": "person",
            "id": "ванесса",
            "aliases": ["Ванесса"],
            "portrait": "Ванесса — ассистент Лича.",
        },
        "## Контекст жизни\n\n- 2026-08-26: Ассистент.\n",
    )
    await index.rebuild_folder(PEOPLE)


@pytest.mark.asyncio
async def test_fetch_semantic_keeps_target_when_self_card_ranks_higher(tmp_path):
    """A named person survives the cap even when the bot's own card (ванесса)
    ranks higher in the vector search — the self-card is dropped first."""
    vault, index = await _seed_vault(tmp_path)
    await _add_veronica(tmp_path, vault, index)
    await _add_vanessa_self(tmp_path, vault, index)
    store = FakeStore(
        [
            {
                "path": "People/ванесса.md",
                "kind": "people",
                "title": "ванесса",
                "score": 0.95,
            },
            {
                "path": "People/вероника.md",
                "kind": "people",
                "title": "вероника",
                "score": 0.5,
            },
        ]
    )
    retriever = KnowledgeRetriever(
        vault,
        index,
        max_blocks=1,
        people_max_blocks=1,
        embeddings=FakeEmbeddings(),
        vector_store=store,
        vector_min_score=0.3,
    )

    blocks = await retriever.fetch_semantic(
        "вероника",
        knowledge_indexes=("people",),
        knowledge_query="вероника",
        people_files=["People/ванесса.md", "People/вероника.md"],
    )

    assert [block.path for block in blocks] == ["People/вероника.md"]


@pytest.mark.asyncio
async def test_fetch_semantic_suppresses_self_card_for_other_person(tmp_path):
    """When the user asks about another person, the bot's own dossier is not
    injected into the compose context."""
    vault, index = await _seed_vault(tmp_path)
    await _add_veronica(tmp_path, vault, index)
    await _add_vanessa_self(tmp_path, vault, index)
    store = FakeStore(
        [
            {
                "path": "People/ванесса.md",
                "kind": "people",
                "title": "ванесса",
                "score": 0.9,
            },
            {
                "path": "People/вероника.md",
                "kind": "people",
                "title": "вероника",
                "score": 0.6,
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
        "что там у вероники",
        knowledge_indexes=("people",),
        knowledge_query="вероника",
        people_files=["People/ванесса.md", "People/вероника.md"],
    )

    paths = [block.path for block in blocks]
    assert "People/вероника.md" in paths
    assert "People/ванесса.md" not in paths


@pytest.mark.asyncio
async def test_fetch_semantic_keeps_self_card_when_about_bot(tmp_path):
    """A query genuinely about the bot still retrieves its own dossier."""
    vault, index = await _seed_vault(tmp_path)
    await _add_vanessa_self(tmp_path, vault, index)
    retriever = KnowledgeRetriever(
        vault,
        index,
        max_blocks=3,
        embeddings=FakeEmbeddings(),
        vector_store=FakeStore([]),
        vector_min_score=0.3,
    )

    blocks = await retriever.fetch_semantic(
        "расскажи про себя",
        knowledge_indexes=("people",),
        knowledge_query="ванесса",
        people_files=["People/ванесса.md"],
    )

    assert [block.path for block in blocks] == ["People/ванесса.md"]


@pytest.mark.asyncio
async def test_fetch_semantic_returns_target_missing_from_vectors(tmp_path):
    """A stale vector index (target absent) cannot drop the named person — the
    deterministic alias path still supplies her dossier."""
    vault, index = await _seed_vault(tmp_path)
    await _add_veronica(tmp_path, vault, index)
    await _add_vanessa_self(tmp_path, vault, index)
    store = FakeStore(
        [
            {
                "path": "People/ванесса.md",
                "kind": "people",
                "title": "ванесса",
                "score": 0.9,
            },
            {
                "path": "People/личь.md",
                "kind": "people",
                "title": "личь",
                "score": 0.7,
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
        "вероника",
        knowledge_indexes=("people",),
        knowledge_query="вероника",
        people_files=["People/вероника.md"],
    )

    paths = [block.path for block in blocks]
    assert "People/вероника.md" in paths


@pytest.mark.asyncio
async def test_fetch_semantic_union_planner_query_when_resolver_misses(tmp_path):
    """If the deterministic resolver only saw the bot's address, the planner's
    knowledge_query still pulls the person it named."""
    vault, index = await _seed_vault(tmp_path)
    await _add_veronica(tmp_path, vault, index)
    await _add_vanessa_self(tmp_path, vault, index)
    retriever = KnowledgeRetriever(
        vault,
        index,
        max_blocks=3,
        embeddings=FakeEmbeddings(),
        vector_store=FakeStore([]),
        vector_min_score=0.3,
    )

    blocks = await retriever.fetch_semantic(
        "вероника",
        knowledge_indexes=("people",),
        knowledge_query="вероника",
        people_files=["People/ванесса.md"],
    )

    paths = [block.path for block in blocks]
    assert "People/вероника.md" in paths


@pytest.mark.asyncio
async def test_fetch_drops_self_card_when_other_person_targeted(tmp_path):
    """Non-embedding fetch path: the bot's own card is dropped when a real
    person is the target."""
    vault, index = await _seed_vault(tmp_path)
    await _add_veronica(tmp_path, vault, index)
    await _add_vanessa_self(tmp_path, vault, index)
    retriever = KnowledgeRetriever(vault, index, max_blocks=3, people_max_blocks=3)

    blocks = await retriever.fetch(
        knowledge_indexes=("people",),
        people_files=["People/ванесса.md", "People/вероника.md"],
    )

    paths = {block.path for block in blocks}
    assert "People/вероника.md" in paths
    assert "People/ванесса.md" not in paths
