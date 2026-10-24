"""The agent saves posted follow-ups as Vanessa's own messages."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from services.agent.broker_worker.posted import PART_STEP, PostedRecorder
from services.agent.broker_worker.worker import TurnDeliveryHandler
from vanessa.contracts.messages import TaskKind, TaskMessage
from vanessa.contracts.posted import PostedMessages
from vanessa.core.hermes_answers import RecentAnswers
from vanessa.infrastructure.broker.backends import Delivery

CHAT_ID = -100
REPLY_TO = 77
POSTED_AT = datetime(2026, 1, 3, 10, 0, tzinfo=UTC)
QUESTION = "what is the build status of the service?"


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


class FakeMessages:
    rows: list[dict]

    def __init__(self, _session) -> None:
        pass

    async def create(self, **row) -> None:
        FakeMessages.rows.append(row)


def _posted(**overrides) -> PostedMessages:
    fields = {
        "telegram_chat_id": CHAT_ID,
        "texts": ["one", "two", "three"],
        "posted_at": POSTED_AT,
        "source": "hermes",
        "reply_to_message_id": REPLY_TO,
        "question": QUESTION,
    }
    return PostedMessages(**{**fields, **overrides})


def _recorder(answers=None) -> tuple[PostedRecorder, FakeSession]:
    FakeMessages.rows = []
    session = FakeSession()
    recorder = PostedRecorder(lambda: session, answers, repository=FakeMessages)
    return recorder, session


async def test_rows_keep_order_and_time() -> None:
    recorder, session = _recorder()
    await recorder.record(_posted())
    rows = FakeMessages.rows
    assert [row["content"] for row in rows] == ["one", "two", "three"]
    assert {row["role"] for row in rows} == {"assistant"}
    assert [row["created_at"] for row in rows] == [
        POSTED_AT,
        POSTED_AT + PART_STEP,
        POSTED_AT + 2 * PART_STEP,
    ]
    assert session.committed is True


async def test_reply_target_only_on_the_first_row() -> None:
    recorder, _ = _recorder()
    await recorder.record(_posted())
    targets = [row["reply_to_message_id"] for row in FakeMessages.rows]
    assert targets == [REPLY_TO, None, None]
    assert {row["channel"] for row in FakeMessages.rows} == {"telegram"}


async def test_lookup_result_is_noted() -> None:
    answers = RecentAnswers(window_seconds=600)
    recorder, _ = _recorder(answers)
    await recorder.record(_posted())
    assert answers.covers(CHAT_ID, QUESTION, "wow")


async def test_reminder_without_question_notes_nothing() -> None:
    answers = MagicMock()
    recorder, _ = _recorder(answers)
    await recorder.record(_posted(question=None, source="reminder"))
    answers.note.assert_not_called()
    assert len(FakeMessages.rows) == len(_posted().texts)


def _handler(posted) -> tuple[TurnDeliveryHandler, MagicMock]:
    pipeline = MagicMock()
    pipeline.run = AsyncMock()
    return TurnDeliveryHandler(MagicMock(), pipeline, MagicMock(), posted), pipeline


def _delivery(message) -> Delivery:
    return Delivery(stream="vanessa:turns", stream_id="1-0", message=message)


async def test_handler_routes_posted_messages() -> None:
    posted = MagicMock()
    posted.record = AsyncMock()
    handler, pipeline = _handler(posted)
    record = _posted()
    await handler.handle(_delivery(record))
    posted.record.assert_awaited_once_with(record)
    pipeline.run.assert_not_awaited()


async def test_handler_without_recorder_drops_posted(caplog) -> None:
    handler, pipeline = _handler(None)
    await handler.handle(_delivery(_posted()))
    pipeline.run.assert_not_awaited()
    assert "broker_unexpected_message kind=posted_messages" in caplog.text


async def test_handler_still_warns_on_other_kinds(caplog) -> None:
    posted = MagicMock()
    posted.record = AsyncMock()
    handler, _ = _handler(posted)
    await handler.handle(_delivery(TaskMessage(task=TaskKind.HERMES_ASK)))
    posted.record.assert_not_awaited()
    assert "broker_unexpected_message" in caplog.text
