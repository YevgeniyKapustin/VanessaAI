import pytest

from vanessa.knowledge.store.store import build_knowledge_store
from vanessa.knowledge.store.store_fs import FilesystemKnowledgeStore
from vanessa.knowledge.store.store_postgres import PostgresKnowledgeStore
from vanessa.knowledge.store.vault import KnowledgeVault
from vanessa.knowledge.users.people_notes import (
    iter_people_notes_fs,
    people_dir,
    people_signature_fs,
)


async def test_filesystem_vault_roundtrip(tmp_path) -> None:
    store = FilesystemKnowledgeStore(str(tmp_path))
    vault = KnowledgeVault(store=store)
    await vault.ensure_structure()
    rel = await vault.write_note(
        "People/ada.md",
        {"id": "ada", "type": "person"},
        "hello",
        mutation_source="test",
    )
    note = await vault.read_note(rel)
    assert note is not None
    assert note.body == "hello"
    notes = await vault.list_notes("People")
    assert notes
    assert vault.list_notes_sync("People")
    assert await vault.notes_signature("People")
    assert vault.notes_signature_sync("People")
    await vault.write_yaml("People/_index.yaml", {"aliases": {}})
    data = await vault.read_yaml("People/_index.yaml")
    assert data["aliases"] == {}
    last_id = 3
    await vault.write_state({"last_message_id": last_id})
    assert (await vault.read_state())["last_message_id"] == last_id
    await vault.write_attachment("inbox/file.bin", b"abc")
    assert await vault.search_fts("hello") == []
    assert vault.root == tmp_path.resolve()


async def test_unconfigured_vault_is_noop() -> None:
    vault = KnowledgeVault(store=FilesystemKnowledgeStore(""))
    assert vault.is_configured is False
    assert vault.root is None
    await vault.ensure_structure()
    assert await vault.read_yaml("x.yaml") == {}
    assert await vault.read_state() == {}
    await vault.write_state({"a": 1})
    assert await vault.read_note("People/a.md") is None
    assert await vault.list_notes("People") == []
    assert vault.list_notes_sync("People") == []
    assert await vault.notes_signature("People") == ()
    assert vault.notes_signature_sync("People") == ()
    assert await vault.search_fts("q") == []
    with pytest.raises(RuntimeError, match="not configured"):
        await vault.write_note("People/a.md", {}, "x")
    with pytest.raises(RuntimeError, match="not configured"):
        await vault.write_yaml("x.yaml", {})
    with pytest.raises(RuntimeError, match="not configured"):
        await vault.write_attachment("a.bin", b"x")


def test_build_store_explicit_and_postgres(monkeypatch, tmp_path) -> None:
    store = FilesystemKnowledgeStore(str(tmp_path))
    assert build_knowledge_store(store=store) is store
    fs = build_knowledge_store(str(tmp_path))
    assert isinstance(fs, FilesystemKnowledgeStore)
    monkeypatch.setattr(
        "vanessa.knowledge.store.store.settings.knowledge_store",
        "postgres",
    )
    pg = build_knowledge_store()
    assert isinstance(pg, PostgresKnowledgeStore)


def test_read_yaml_invalid_and_non_dict(tmp_path) -> None:
    store = FilesystemKnowledgeStore(str(tmp_path))
    (tmp_path / "People").mkdir()
    store._ready = True
    store._root = tmp_path
    broken = tmp_path / "People" / "bad.yaml"
    broken.write_text(":\n  [", encoding="utf-8")
    data = store._read_yaml_sync("People/bad.yaml")
    assert data == {}
    listed = tmp_path / "People" / "list.yaml"
    listed.write_text("- a\n", encoding="utf-8")
    assert store._read_yaml_sync("People/list.yaml") == {}
    assert store._read_yaml_sync("People/missing.yaml") == {}


def test_people_notes_fs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "vanessa.knowledge.users.people_notes.settings.knowledge_path",
        "",
    )
    assert people_dir() is None
    assert iter_people_notes_fs() == []
    assert people_signature_fs() == ()
    people = tmp_path / "People"
    people.mkdir()
    (people / "ada.md").write_text("---\nid: ada\n---\nbody\n", encoding="utf-8")
    (people / "_index.yaml").write_text("aliases: {}\n", encoding="utf-8")
    monkeypatch.setattr(
        "vanessa.knowledge.users.people_notes.settings.knowledge_path",
        str(tmp_path),
    )
    notes = list(iter_people_notes_fs())
    assert notes
    signature = people_signature_fs()
    assert signature
