from unittest.mock import MagicMock

from app.contracts.messages import TaskKind
from app.core.messages import StoredMessage
from app.services.indexing.message_indexing import MessageIndexingService


class _FakeDispatcher:
    def __init__(self) -> None:
        self.submissions: list[tuple] = []

    def submit(self, task, payload, *, dedup_key=None) -> None:
        self.submissions.append((task, payload, dedup_key))


def _message() -> StoredMessage:
    return StoredMessage(
        id=7,
        role="user",
        content="hello",
        qdrant_point_id="old-point",
    )


def test_schedule_publishes_with_dispatcher() -> None:
    dispatcher = _FakeDispatcher()
    svc = MessageIndexingService(
        indexer=MagicMock(),
        messages=MagicMock(),
        session_factory=MagicMock(),
        dispatcher=dispatcher,
    )
    svc.schedule(_message())
    assert len(dispatcher.submissions) == 1
    task, payload, dedup_key = dispatcher.submissions[0]
    assert task == TaskKind.INDEX_MESSAGE
    assert payload["message_id"] == 7
    assert payload["role"] == "user"
    assert payload["content"] == "hello"
    assert payload["point_id"] == "old-point"
    assert dedup_key == "index:7"


def test_schedule_uses_background_without_dispatcher() -> None:
    background = MagicMock()
    svc = MessageIndexingService(
        indexer=MagicMock(),
        messages=MagicMock(),
        session_factory=MagicMock(),
        background=background,
    )
    svc.schedule(_message())
    background.submit.assert_called_once()


def test_schedule_skips_non_user_role() -> None:
    dispatcher = _FakeDispatcher()
    svc = MessageIndexingService(
        indexer=MagicMock(),
        messages=MagicMock(),
        session_factory=MagicMock(),
        dispatcher=dispatcher,
    )
    svc.schedule(StoredMessage(id=8, role="assistant", content="x"))
    assert dispatcher.submissions == []
