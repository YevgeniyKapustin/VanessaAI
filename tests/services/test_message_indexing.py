import pytest

from app.core.messages import StoredMessage
from app.services.indexing.message_indexing import MessageIndexingService


class FakeIndexer:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def index(
        self,
        message_id: int,
        role: str,
        content: str,
        point_id: str | None = None,
    ) -> str:
        self.calls.append(message_id)
        return f"point-{message_id}"


class FakeRepo:
    def __init__(self) -> None:
        self.updated: list[tuple[int, str]] = []

    async def update_qdrant_point_id(self, message_id: int, point_id: str) -> None:
        self.updated.append((message_id, point_id))


@pytest.mark.asyncio
async def test_background_indexing_commits_in_separate_session(monkeypatch):
    indexer = FakeIndexer()
    committed: list[bool] = []
    updated: list[tuple[int, str]] = []

    class FakeMessageRepository:
        def __init__(self, session: object) -> None:
            self._session = session

        async def update_qdrant_point_id(
            self,
            message_id: int,
            point_id: str,
        ) -> None:
            updated.append((message_id, point_id))

    class FakeSession:
        async def commit(self) -> None:
            committed.append(True)

        async def __aenter__(self) -> "FakeSession":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    def session_factory() -> FakeSession:
        return FakeSession()

    monkeypatch.setattr(
        "app.services.indexing.message_indexing.MessageRepository",
        FakeMessageRepository,
    )
    service = MessageIndexingService(
        indexer=indexer,
        messages=FakeRepo(),
        session_factory=session_factory,
        max_retries=0,
    )
    record = StoredMessage(id=7, role="user", content="hello")

    await service._index_in_background(record)

    assert indexer.calls == [7]
    assert updated == [(7, "point-7")]
    assert committed == [True]


@pytest.mark.asyncio
async def test_index_now_updates_repository():
    indexer = FakeIndexer()
    repo = FakeRepo()
    service = MessageIndexingService(
        indexer=indexer,
        messages=repo,
        session_factory=None,
        max_retries=0,
    )
    record = StoredMessage(id=7, role="user", content="hello")

    await service.index_now(record)

    assert indexer.calls == [7]
    assert repo.updated == [(7, "point-7")]
