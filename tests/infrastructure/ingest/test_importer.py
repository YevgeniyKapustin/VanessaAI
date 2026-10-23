from datetime import UTC, datetime

import pytest

from vanessa.core.messages import StoredMessage
from vanessa.infrastructure.ingest.importer import HistoryImporter
from vanessa.infrastructure.ingest.telegram_export import ParsedExportMessage


class FakeUow:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class FakeMessages:
    def __init__(self) -> None:
        self._next_id = 1
        self.created: list[StoredMessage] = []
        self.existing: set[int] = set()

    async def get_existing_telegram_message_ids(
        self,
        telegram_message_ids: list[int],
    ) -> set[int]:
        return {mid for mid in telegram_message_ids if mid in self.existing}

    async def create(self, **kwargs) -> StoredMessage:
        message = StoredMessage(
            id=self._next_id,
            role=kwargs["role"],
            content=kwargs["content"],
            sender_telegram_id=kwargs.get("sender_telegram_id"),
            telegram_message_id=kwargs.get("telegram_message_id"),
            created_at=kwargs.get("created_at"),
        )
        self._next_id += 1
        self.created.append(message)
        return message


class FakeUsers:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def get_or_create(self, telegram_id: int, **kwargs) -> object:
        _ = kwargs
        self.calls.append(telegram_id)
        return object()


def _parsed(message_id: int, text: str = "hello") -> ParsedExportMessage:
    return ParsedExportMessage(
        telegram_message_id=message_id,
        sender_telegram_id=100 + message_id,
        sender_display_name="User",
        content=text,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_importer_imports_batches():
    uow = FakeUow()
    messages = FakeMessages()
    users = FakeUsers()
    importer = HistoryImporter(
        messages=messages,
        users=users,
        unit_of_work=uow,
        batch_size=2,
    )
    parsed = [_parsed(1), _parsed(2), _parsed(3)]
    imported, skipped = await importer.import_messages(parsed)
    assert imported == len(parsed)
    assert skipped == 0
    assert len(users.calls) == len(parsed)
    expected_commits = (
        len(parsed) + importer._batch_size - 1
    ) // importer._batch_size
    assert uow.commits == expected_commits
    assert [m.telegram_message_id for m in messages.created] == [1, 2, 3]


@pytest.mark.asyncio
async def test_importer_skips_existing_telegram_ids():
    messages = FakeMessages()
    messages.existing = {2}
    importer = HistoryImporter(
        messages=messages,
        users=FakeUsers(),
        unit_of_work=FakeUow(),
        batch_size=10,
    )
    imported, skipped = await importer.import_messages([_parsed(1), _parsed(2)])
    assert imported == 1
    assert skipped == 1
