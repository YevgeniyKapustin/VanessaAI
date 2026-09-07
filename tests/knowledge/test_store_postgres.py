from typing import Self

from vanessa.knowledge.schema import VaultNote
from vanessa.knowledge.store.store_postgres import PostgresKnowledgeStore, run_coro_sync


class _Session:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def commit(self) -> None:
        return None


class _Service:
    def __init__(self, session) -> None:
        del session
        self.notes: dict[str, VaultNote] = {}
        self.docs: dict[str, dict] = {}

    async def upsert_note_doc(self, note: VaultNote) -> VaultNote:
        self.notes[note.relative_path] = note
        return note

    async def get_note(self, relative_path: str) -> VaultNote | None:
        return self.notes.get(relative_path)

    async def list_notes(self, folder: str, *, recursive: bool = False):
        del recursive
        return [
            note
            for path, note in self.notes.items()
            if path.startswith(folder)
        ]

    async def notes_signature(self, folder: str) -> tuple:
        return tuple(path for path in self.notes if path.startswith(folder))

    async def read_document(self, path: str) -> dict:
        return self.docs.get(path, {})

    async def write_document(self, path: str, data: dict) -> str:
        self.docs[path] = data
        return path

    async def search_fts(self, query: str, **kwargs):
        del query, kwargs
        return list(self.notes.values())


def _store(monkeypatch, tmp_path=None, *, notes=None, docs=None) -> PostgresKnowledgeStore:
    shared_notes = notes if notes is not None else {}
    shared_docs = docs if docs is not None else {}

    class BoundService(_Service):
        def __init__(self, session) -> None:
            del session
            self.notes = shared_notes
            self.docs = shared_docs

    monkeypatch.setattr(
        "vanessa.infrastructure.db.session.async_session_factory",
        _Session,
    )
    monkeypatch.setattr(
        "vanessa.knowledge.store.store_postgres.KnowledgeService",
        BoundService,
    )
    root = str(tmp_path) if tmp_path is not None else None
    return PostgresKnowledgeStore(filesystem_root=root)


async def test_postgres_store_note_yaml_and_search(tmp_path, monkeypatch) -> None:
    store = _store(monkeypatch, tmp_path)
    assert store.is_configured is True
    await store.ensure_structure()
    rel = await store.write_note("People/ada.md", {"id": "ada"}, "hi")
    assert rel.endswith("ada.md")
    assert await store.read_note("People/ada.md") is not None
    assert await store.list_notes("People")
    assert await store.notes_signature("People")
    assert store.list_notes_sync("People")
    assert store.notes_signature_sync("People")
    await store.write_yaml("People/_index.yaml", {"a": 1})
    assert await store.read_yaml("People/_index.yaml") == {"a": 1}
    await store.write_state({"k": 1})
    assert await store.read_state() == {"k": 1}
    await store.write_attachment("inbox/x.bin", b"abc")
    assert await store.search_fts("hi")


async def test_postgres_attachment_without_filesystem(monkeypatch) -> None:
    store = _store(monkeypatch)
    path = await store.write_attachment("inbox/x.bin", b"abc")
    assert path.endswith("x.bin")


def test_run_coro_sync_outside_loop() -> None:
    expected = 7

    async def value():
        return expected

    assert run_coro_sync(value) == expected
