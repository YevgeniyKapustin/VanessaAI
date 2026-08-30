import asyncio
from typing import Self
from unittest.mock import AsyncMock, MagicMock

import pytest

from vanessa.contracts.messages import TaskKind, TaskMessage
from vanessa.infrastructure.broker.serialization import encode
from vanessa.infrastructure.db.models import OutboxEvent
from vanessa.infrastructure.outbox.relay import OutboxRelay
from vanessa.infrastructure.outbox.repository import OutboxRepository

# --- repository ---------------------------------------------------------------

async def test_add_stages_message() -> None:
    session = AsyncMock()
    # ``session.add`` is a synchronous method in SQLAlchemy; keep it a plain mock.
    session.add = MagicMock()
    repo = OutboxRepository(session)
    message = TaskMessage(task=TaskKind.SWEEP, correlation_id="c1")
    repo.add(stream="tasks", message=message)
    added: OutboxEvent = session.add.call_args[0][0]
    assert isinstance(added, OutboxEvent)
    assert added.stream == "tasks"
    assert added.kind == "task"
    assert added.message_id == message.message_id
    assert added.correlation_id == "c1"
    assert added.fields["kind"] == "task"


async def test_claim_batch_returns_rows() -> None:
    session = AsyncMock()
    events = [
        OutboxEvent(id=1, stream="tasks", kind="task", message_id="a", correlation_id="c"),
        OutboxEvent(id=2, stream="tasks", kind="task", message_id="b", correlation_id="c"),
    ]
    result = MagicMock()
    result.scalars.return_value.all.return_value = events
    session.execute = AsyncMock(return_value=result)
    repo = OutboxRepository(session)
    got = await repo.claim_batch(batch_size=5)
    assert got == events


async def test_mark_failed_retries_then_fails() -> None:
    session = AsyncMock()
    event = OutboxEvent(id=1, attempts=4, status="pending")
    session.get = AsyncMock(return_value=event)
    repo = OutboxRepository(session)
    await repo.mark_failed(1, "boom", max_attempts=5)
    assert event.attempts == 5
    assert event.status == "failed"
    assert event.last_error == "boom"


async def test_mark_failed_keeps_pending_below_cap() -> None:
    session = AsyncMock()
    event = OutboxEvent(id=1, attempts=0, status="pending")
    session.get = AsyncMock(return_value=event)
    repo = OutboxRepository(session)
    await repo.mark_failed(1, "transient", max_attempts=5)
    assert event.attempts == 1
    assert event.status == "pending"


async def test_count_pending() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [1, 2, 3]
    session.execute = AsyncMock(return_value=result)
    repo = OutboxRepository(session)
    assert await repo.count_pending() == 3


# --- relay ---------------------------------------------------------------------

class _FakeSession:
    """Minimal async-context-manager session for the relay tests."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _relay(monkeypatch, *, repo, publish):
    monkeypatch.setattr("vanessa.infrastructure.outbox.relay.OutboxRepository", lambda session: repo)
    broker = MagicMock()
    broker.publish = publish
    session = _FakeSession()
    relay = OutboxRelay(broker, MagicMock(return_value=session), poll_seconds=0.01)
    return relay, session


async def test_flush_once_publishes_and_marks_delivered(monkeypatch) -> None:
    message = TaskMessage(task=TaskKind.SWEEP, correlation_id="c1")
    event = OutboxEvent(
        id=1, stream="tasks", kind="task", message_id=message.message_id,
        correlation_id="c1", fields=encode(message),
    )
    repo = MagicMock()
    repo.claim_batch = AsyncMock(return_value=[event])
    repo.mark_delivered = AsyncMock()
    repo.mark_failed = AsyncMock()
    publish = AsyncMock(return_value="1-0")

    relay, session = _relay(monkeypatch, repo=repo, publish=publish)
    published = await relay.flush_once()

    assert published == 1
    publish.assert_awaited_once_with("tasks", message)
    repo.mark_delivered.assert_awaited_once_with(1)
    assert session.committed


async def test_flush_once_marks_failed_on_publish_error(monkeypatch) -> None:
    message = TaskMessage(task=TaskKind.SWEEP)
    event = OutboxEvent(
        id=2, stream="tasks", kind="task", message_id=message.message_id,
        correlation_id="c2", fields=encode(message),
    )
    repo = MagicMock()
    repo.claim_batch = AsyncMock(return_value=[event])
    repo.mark_delivered = AsyncMock()
    repo.mark_failed = AsyncMock()

    relay, session = _relay(
        monkeypatch, repo=repo, publish=AsyncMock(side_effect=RuntimeError("redis down"))
    )
    published = await relay.flush_once()

    assert published == 0
    repo.mark_failed.assert_awaited_once()
    assert session.committed


async def test_flush_once_empty_releases_locks(monkeypatch) -> None:
    repo = MagicMock()
    repo.claim_batch = AsyncMock(return_value=[])
    relay, session = _relay(monkeypatch, repo=repo, publish=AsyncMock())
    published = await relay.flush_once()
    assert published == 0
    assert session.rolled_back
    assert not session.committed


async def test_run_forever_loops_until_cancelled(monkeypatch) -> None:
    repo = MagicMock()
    repo.claim_batch = AsyncMock(return_value=[])
    relay, _ = _relay(monkeypatch, repo=repo, publish=AsyncMock())
    task = asyncio.create_task(relay.run_forever())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
