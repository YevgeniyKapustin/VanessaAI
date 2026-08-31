from unittest.mock import MagicMock

from vanessa.config import settings
from vanessa.knowledge.store import PostgresKnowledgeStore, build_knowledge_store


def test_postgres_store_does_not_use_knowledge_path(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "knowledge_store", "postgres")
    monkeypatch.setattr(settings, "knowledge_path", str(tmp_path / "knowledge"))
    monkeypatch.setattr(
        "vanessa.infrastructure.db.session.async_session_factory",
        MagicMock(),
    )
    store = build_knowledge_store()
    assert isinstance(store, PostgresKnowledgeStore)
    assert store.filesystem_root is None


async def test_postgres_ensure_structure_does_not_mkdir(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "knowledge_path", str(tmp_path / "knowledge"))
    monkeypatch.setattr(
        "vanessa.infrastructure.db.session.async_session_factory",
        MagicMock(),
    )
    store = PostgresKnowledgeStore()
    await store.ensure_structure()
    assert not (tmp_path / "knowledge").exists()
