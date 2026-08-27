import pytest

from app.knowledge.vault import KnowledgeVault
from app.knowledge.vector_index import KnowledgeVectorIndexer, knowledge_kind_for_path


class FakeEmbeddings:
    def __init__(self) -> None:
        self.embedded: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.embedded.append(text)
        return [float(len(text))] * 4

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return [[float(len(text))] * 4 for text in texts]


class FakeKnowledgeStore:
    def __init__(self) -> None:
        self.notes: dict[str, tuple[str, str, list[float]]] = {}
        self.chunk_points: dict[tuple[str, int], tuple[str, str, list[float]]] = {}
        self.ensured = False

    async def ensure_collection(self) -> None:
        self.ensured = True

    async def upsert_note(
        self,
        path: str,
        kind: str,
        title: str,
        vector: list[float],
    ) -> str:
        self.notes[path] = (kind, title, vector)
        return path

    async def upsert_notes(
        self,
        items: list[tuple[str, str, str, list[float]]],
    ) -> list[str]:
        for path, kind, title, vector in items:
            self.notes[path] = (kind, title, vector)
        return [path for path, _, _, _ in items]

    async def upsert_note_chunks(
        self,
        path: str,
        kind: str,
        title: str,
        chunks: list[tuple[int, str]],
        vectors: list[list[float]],
    ) -> list[str]:
        for (index, _), vector in zip(chunks, vectors):
            self.chunk_points[(path, index)] = (kind, title, vector)
        return [f"{path}#{index}" for index, _ in chunks]

    async def search(self, vector: list[float], limit: int = 30) -> list[dict]:
        del vector
        hits = []
        for i, (path, (kind, title, _)) in enumerate(self.notes.items()):
            hits.append(
                {
                    "path": path,
                    "kind": kind,
                    "title": title,
                    "score": max(0.0, 0.95 - i * 0.1),
                }
            )
        for (path, index), (kind, title, _) in self.chunk_points.items():
            hits.append(
                {
                    "path": path,
                    "kind": kind,
                    "title": title,
                    "chunk_index": index,
                    "score": max(0.0, 0.95 - len(hits) * 0.1),
                }
            )
        return hits[:limit]


def test_knowledge_kind_for_path():
    assert knowledge_kind_for_path("People/личь.md") == "people"
    assert knowledge_kind_for_path("Lore/events/x.md") == "lore"
    assert knowledge_kind_for_path("Culture/games/y.md") == "culture"
    assert knowledge_kind_for_path("Logs/daily/z.md") == "logs"
    assert knowledge_kind_for_path("inbox/note.md") is None


async def _seed_vault(tmp_path) -> KnowledgeVault:
    vault = KnowledgeVault(str(tmp_path))
    await vault.write_note(
        "People/личь.md",
        {"type": "person", "id": "личь"},
        "## Контекст жизни\n\n- 2026-08-26: Философ и сварщик.\n- 2026-08-26: Играет в ХСР.\n",
    )
    await vault.write_note(
        "Lore/events/2026-01-01-тест-ивент.md",
        {"type": "event", "id": "тест-ивент", "title": "тест ивент", "date": "2026-01-01"},
        "## Суть\n\n- 2026-01-01: Обсуждение игры.\n",
    )
    await vault.write_note(
        "Culture/games/игра.md",
        {"type": "recommendation", "id": "игра", "title": "Игра"},
        "## Описание\n\n- Стратегия.\n",
    )
    await vault.write_note(
        "Logs/daily/2026-01-01.md",
        {"type": "log", "period": "daily"},
        "## Темы\n\n- Прошли катку.\n",
    )
    return vault


@pytest.mark.asyncio
async def test_index_all_embeds_semantic_notes(tmp_path):
    vault = await _seed_vault(tmp_path)
    embeddings = FakeEmbeddings()
    store = FakeKnowledgeStore()
    indexer = KnowledgeVectorIndexer(vault, embeddings, store)

    count = await indexer.index_all()

    assert count == 4
    assert store.ensured is True
    assert set(store.notes) == {
        "People/личь.md",
        "Lore/events/2026-01-01-тест-ивент.md",
        "Culture/games/игра.md",
        "Logs/daily/2026-01-01.md",
    }
    kind, title, _ = store.notes["People/личь.md"]
    assert kind == "people"
    assert title == "личь"
    # Embed text carries the kind prefix and the note body.
    assert any(text.startswith("[people] личь") for text in embeddings.embedded)


@pytest.mark.asyncio
async def test_index_note_reindexes_single_note(tmp_path):
    vault = await _seed_vault(tmp_path)
    store = FakeKnowledgeStore()
    indexer = KnowledgeVectorIndexer(vault, FakeEmbeddings(), store)

    ok = await indexer.index_note("People/личь.md")

    assert ok is True
    assert list(store.notes) == ["People/личь.md"]

    # Non-semantic paths are ignored.
    assert await indexer.index_note("inbox/note.md") is False


@pytest.mark.asyncio
async def test_embed_text_is_capped(tmp_path):
    vault = await _seed_vault(tmp_path)
    store = FakeKnowledgeStore()
    indexer = KnowledgeVectorIndexer(vault, FakeEmbeddings(), store, max_chars=30)

    text = indexer._embed_text("people", "личь", "x" * 200)

    assert len(text) == 30


@ pytest.mark.asyncio
async def test_index_all_chunks_long_people_dossier(tmp_path):
    vault = await _seed_vault(tmp_path)
    # A long dossier that exceeds the per-chunk budget -> split into blocks.
    long_body = "\n".join(
        f"- 2026-08-{day:02d}: Факт номер {day} про лича." for day in range(1, 40)
    )
    await vault.write_note(
        "People/личь.md",
        {"type": "person", "id": "личь", "aliases": ["Личь"]},
        long_body,
    )
    store = FakeKnowledgeStore()
    indexer = KnowledgeVectorIndexer(
        vault,
        FakeEmbeddings(),
        store,
        people_chunk_chars=120,
        people_chunk_overlap=20,
    )

    await indexer.index_note("People/личь.md")

    assert store.chunk_points, "expected chunk points for a long people dossier"
    indexes = sorted(index for (_, index) in store.chunk_points)
    assert indexes == list(range(len(indexes)))
    # Every chunk was embedded (not just the single whole-note).
    assert len(store.chunk_points) > 1


@ pytest.mark.asyncio
async def test_index_all_short_people_dossier_uses_whole_note(tmp_path):
    vault = await _seed_vault(tmp_path)
    store = FakeKnowledgeStore()
    indexer = KnowledgeVectorIndexer(
        vault,
        FakeEmbeddings(),
        store,
        people_chunk_chars=2000,
    )

    ok = await indexer.index_note("People/личь.md")

    assert ok is True
    assert "People/личь.md" in store.notes
    assert store.chunk_points == {}
