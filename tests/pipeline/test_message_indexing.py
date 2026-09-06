import asyncio
from typing import Self

import pytest

from vanessa.core.messages import StoredMessage
from vanessa.pipeline.background import BackgroundExecutor
from vanessa.pipeline.indexing.message_indexing import MessageIndexingService


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
        _ = role, content, point_id
        self.calls.append(message_id)
        return f"point-{message_id}"


class FakeRepo:
    def __init__(self) -> None:
        self.updated: list[tuple[int, str]] = []

    async def update_qdrant_point_id(self, message_id: int, point_id: str) -> None:
        self.updated.append((message_id, point_id))


class _CommitSession:
    def __init__(self, committed: list[bool]) -> None:
        self._committed = committed

    async def commit(self) -> None:
        self._committed.append(True)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


def _session_factory_for(committed: list[bool]):
    def session_factory() -> _CommitSession:
        return _CommitSession(committed)

    return session_factory


def _point_id_repository_cls(updated: list[tuple[int, str]]):
    class FakeMessageRepository:
        def __init__(self, session: object) -> None:
            self._session = session

        async def update_qdrant_point_id(
            self,
            message_id: int,
            point_id: str,
        ) -> None:
            updated.append((message_id, point_id))

    return FakeMessageRepository


@pytest.mark.asyncio
async def test_background_indexing_commits_in_separate_session(monkeypatch):
    indexer = FakeIndexer()
    committed: list[bool] = []
    updated: list[tuple[int, str]] = []

    monkeypatch.setattr(
        "vanessa.pipeline.indexing.message_indexing.MessageRepository",
        _point_id_repository_cls(updated),
    )
    service = MessageIndexingService(
        indexer=indexer,
        messages=FakeRepo(),
        session_factory=_session_factory_for(committed),
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


@pytest.mark.asyncio
async def test_index_now_skips_non_user_role():
    indexer = FakeIndexer()
    repo = FakeRepo()
    service = MessageIndexingService(
        indexer=indexer,
        messages=repo,
        session_factory=None,
        max_retries=0,
    )
    record = StoredMessage(id=7, role="assistant", content="bot")

    await service.index_now(record)

    assert indexer.calls == []
    assert repo.updated == []


@pytest.mark.asyncio
async def test_embed_with_retry_retries_then_succeeds():
    calls = {"count": 0}

    class FlakyIndexer:
        async def index(
            self,
            message_id: int,
            role: str,
            content: str,
            point_id: str | None = None,
        ) -> str:
            _ = message_id, role, content, point_id
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("temporary")
            return "point-ok"

    service = MessageIndexingService(
        indexer=FlakyIndexer(),
        messages=FakeRepo(),
        session_factory=None,
        max_retries=1,
    )
    record = StoredMessage(id=1, role="user", content="x")

    point_id = await service._embed_with_retry(record)

    assert point_id == "point-ok"
    expected_attempts = 2
    assert calls["count"] == expected_attempts


@pytest.mark.asyncio
async def test_embed_with_retry_returns_existing_point_for_non_user():
    class NeverIndexer:
        async def index(self, *args: object, **kwargs: object) -> str:
            _ = args, kwargs
            raise AssertionError("should not index")

    service = MessageIndexingService(
        indexer=NeverIndexer(),
        messages=FakeRepo(),
        session_factory=None,
        max_retries=0,
    )
    record = StoredMessage(
        id=1,
        role="assistant",
        content="x",
        qdrant_point_id="keep",
    )

    assert await service._embed_with_retry(record) == "keep"


@pytest.mark.asyncio
async def test_schedule_creates_background_task(monkeypatch):
    scheduled: list[StoredMessage] = []
    tasks: list[asyncio.Task] = []
    original_create_task = asyncio.create_task

    async def fake_background(self, record: StoredMessage) -> None:
        scheduled.append(record)

    def capture_task(coro):
        task = original_create_task(coro)
        tasks.append(task)
        return task

    monkeypatch.setattr(
        MessageIndexingService,
        "_index_in_background",
        fake_background,
    )
    monkeypatch.setattr(asyncio, "create_task", capture_task)
    service = MessageIndexingService(
        indexer=FakeIndexer(),
        messages=FakeRepo(),
        session_factory=lambda: None,
        max_retries=0,
    )
    record = StoredMessage(id=3, role="user", content="hi")
    service.schedule(record)
    await asyncio.gather(*tasks)

    assert scheduled == [record]


@pytest.mark.asyncio
async def test_schedule_skips_non_user_role():
    service = MessageIndexingService(
        indexer=FakeIndexer(),
        messages=FakeRepo(),
        session_factory=lambda: None,
        max_retries=0,
    )
    service.schedule(StoredMessage(id=1, role="assistant", content="x"))


@pytest.mark.asyncio
async def test_index_now_logs_and_swallows_errors(caplog):
    class FailingIndexer:
        async def index(self, *args: object, **kwargs: object) -> str:
            _ = args, kwargs
            raise RuntimeError("embed failed")

    repo = FakeRepo()
    service = MessageIndexingService(
        indexer=FailingIndexer(),
        messages=repo,
        session_factory=None,
        max_retries=0,
    )
    record = StoredMessage(id=7, role="user", content="hello")

    await service.index_now(record)

    assert repo.updated == []


@pytest.mark.asyncio
async def test_background_indexing_swallows_errors(monkeypatch):
    class FailingIndexer:
        async def index(self, *args: object, **kwargs: object) -> str:
            _ = args, kwargs
            raise RuntimeError("background fail")

    service = MessageIndexingService(
        indexer=FailingIndexer(),
        messages=FakeRepo(),
        session_factory=lambda: None,
        max_retries=0,
    )
    record = StoredMessage(id=7, role="user", content="hello")

    await service._index_in_background(record)


@pytest.mark.asyncio
async def test_schedule_submits_to_background_executor(monkeypatch):
    indexer = FakeIndexer()
    updated: list[tuple[int, str]] = []
    committed: list[bool] = []

    monkeypatch.setattr(
        "vanessa.pipeline.indexing.message_indexing.MessageRepository",
        _point_id_repository_cls(updated),
    )
    executor = BackgroundExecutor(maxsize=10, workers=1)
    executor.start()
    try:
        service = MessageIndexingService(
            indexer=indexer,
            messages=FakeRepo(),
            session_factory=_session_factory_for(committed),
            max_retries=0,
            background=executor,
        )
        record = StoredMessage(id=7, role="user", content="hello")
        service.schedule(record)
        await executor.join()
    finally:
        await executor.shutdown()

    assert indexer.calls == [7]
    assert updated == [(7, "point-7")]
    assert committed == [True]
