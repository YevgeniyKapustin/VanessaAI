
from vanessa.contracts.messages import TaskKind, TaskMessage
from services.worker.handlers import (
    IndexMessageHandler,
    PortraitHandler,
    ReindexKnowledgeHandler,
    SweepHandler,
)


class _FakeSession:
    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def commit(self) -> None:
        pass


class _FakeEmbeddings:
    async def embed(self, content):
        return [0.1, 0.2]


class _FakeVectorStore:
    async def upsert_message(self, **kwargs):
        return "point-1"


class _FakeRepo:
    def __init__(self, session) -> None:
        self.updated: list[tuple[int, str]] = []

    async def update_qdrant_point_id(self, message_id, point_id) -> None:
        self.updated.append((message_id, point_id))


async def test_index_message_handler(monkeypatch) -> None:
    from vanessa.infrastructure.db import repository

    fake_repo = _FakeRepo(None)
    monkeypatch.setattr(repository, "MessageRepository", lambda session: fake_repo)

    session = _FakeSession()
    handler = IndexMessageHandler(
        _FakeEmbeddings(),
        _FakeVectorStore(),
        lambda: session,
        max_retries=2,
    )
    task = TaskMessage(
        task=TaskKind.INDEX_MESSAGE,
        payload={
            "message_id": 7,
            "role": "user",
            "content": "hello",
            "point_id": None,
        },
    )
    await handler.handle(task)
    assert fake_repo.updated == [(7, "point-1")]


async def test_index_message_handler_skips_non_user_role() -> None:
    handler = IndexMessageHandler(_FakeEmbeddings(), _FakeVectorStore(), None)
    task = TaskMessage(
        task=TaskKind.INDEX_MESSAGE,
        payload={"message_id": 7, "role": "assistant", "content": "hi", "point_id": "p"},
    )
    # No session factory configured — would raise if it tried to update.
    await handler.handle(task)


async def test_sweep_handler_runs_once(monkeypatch) -> None:
    from vanessa.infrastructure.db import repository

    class _FakeSweep:
        def __init__(self) -> None:
            self.runs = 0

        async def run(self, repo):
            self.runs += 1
            return 3

    fake_sweep = _FakeSweep()
    monkeypatch.setattr(repository, "MessageRepository", lambda session: object())
    session = _FakeSession()
    handler = SweepHandler(fake_sweep, lambda: session)
    await handler.handle(TaskMessage(task=TaskKind.SWEEP, payload={}))
    assert fake_sweep.runs == 1


async def test_portrait_handler_runs_builder() -> None:
    class _FakeBuilder:
        def __init__(self) -> None:
            self.runs = 0

        async def run(self, *, force: bool = False):
            self.runs += 1
            return 2

    builder = _FakeBuilder()
    await PortraitHandler(builder).handle(TaskMessage(task=TaskKind.PORTRAIT, payload={}))
    assert builder.runs == 1


async def test_reindex_knowledge_handler() -> None:
    class _FakeIndexer:
        def __init__(self) -> None:
            self.runs = 0

        async def index_all(self):
            self.runs += 1

    indexer = _FakeIndexer()
    await ReindexKnowledgeHandler(indexer).handle(
        TaskMessage(task=TaskKind.REINDEX_KNOWLEDGE, payload={})
    )
    assert indexer.runs == 1
