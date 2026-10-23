
from typing import Self

from services.worker.handlers import (
    InboxNoteHandler,
    PortraitHandler,
    SweepHandler,
)
from vanessa.contracts.messages import InboxNoteReply, TaskKind, TaskMessage
from vanessa.infrastructure.db import repository


class _FakeSession:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def commit(self) -> None:
        pass


async def test_sweep_handler_runs_once(monkeypatch) -> None:
    class _FakeSweep:
        def __init__(self) -> None:
            self.runs = 0

        async def run(self, repo):
            _ = repo
            self.runs += 1
            return 3

    fake_sweep = _FakeSweep()
    monkeypatch.setattr(repository, "MessageRepository", lambda _session: object())
    session = _FakeSession()
    handler = SweepHandler(fake_sweep, lambda: session)
    await handler.handle(TaskMessage(task=TaskKind.SWEEP, payload={}))
    assert fake_sweep.runs == 1


async def test_portrait_handler_runs_builder() -> None:
    class _FakeBuilder:
        def __init__(self) -> None:
            self.runs = 0

        async def run(self, *, force: bool = False):
            _ = force
            self.runs += 1
            return 2

    builder = _FakeBuilder()
    await PortraitHandler(builder).handle(TaskMessage(task=TaskKind.PORTRAIT, payload={}))
    assert builder.runs == 1


async def test_inbox_note_handler_replies(monkeypatch) -> None:
    async def fake_save(vault, **kwargs):
        return "inbox/saved.md"

    monkeypatch.setattr("services.worker.handlers.inbox.save_inbox_note", fake_save)

    published: list = []

    class _Broker:
        async def publish(self, stream, message) -> None:
            published.append((stream, message))

    handler = InboxNoteHandler(object(), _Broker())
    task = TaskMessage(
        task=TaskKind.INBOX_NOTE,
        correlation_id="n1",
        payload={"text": "hi"},
        reply_to="replies:n1",
    )
    await handler.handle(task)
    assert published[0][0] == "replies:n1"
    reply = published[0][1]
    assert isinstance(reply, InboxNoteReply)
    assert reply.ok is True
    assert reply.path == "inbox/saved.md"
