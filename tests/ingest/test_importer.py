from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.messages import StoredMessage
from app.ingest.importer import HistoryImporter
from app.ingest.telegram_export import ParsedExportMessage


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
        self.point_updates: list[tuple[int, str]] = []

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

    async def update_qdrant_point_id(self, message_id: int, point_id: str) -> None:
        self.point_updates.append((message_id, point_id))


class FakeUsers:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def get_or_create(self, telegram_id: int, **kwargs) -> object:
        self.calls.append(telegram_id)
        return object()


class FakeEmbeddings:
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


class FakeVectorStore:
    def __init__(self) -> None:
        self.batches: list[list[tuple[int, list[float], str | None]]] = []

    async def ensure_collection(self) -> None:
        return None

    async def upsert_batch(
        self,
        items: list[tuple[int, list[float], str | None]],
    ) -> list[str]:
        self.batches.append(items)
        return [f"pt-{message_id}" for message_id, _, _ in items]


def _parsed(message_id: int, text: str = "hello") -> ParsedExportMessage:
    return ParsedExportMessage(
        telegram_message_id=message_id,
        sender_telegram_id=100 + message_id,
        sender_display_name="User",
        content=text,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_importer_imports_and_embeds_batch():
    uow = FakeUow()
    messages = FakeMessages()
    users = FakeUsers()
    vectors = FakeVectorStore()
    importer = HistoryImporter(
        messages=messages,
        users=users,
        embeddings=FakeEmbeddings(),
        vector_store=vectors,
        unit_of_work=uow,
        batch_size=2,
    )
    imported, skipped = await importer.import_messages(
        [_parsed(1), _parsed(2), _parsed(3)],
        embed=True,
    )
    assert imported == 3
    assert skipped == 0
    assert len(users.calls) == 3
    assert uow.commits == 2
    assert messages.point_updates == [(1, "pt-1"), (2, "pt-2"), (3, "pt-3")]


@pytest.mark.asyncio
async def test_importer_skips_existing_telegram_ids():
    messages = FakeMessages()
    messages.existing = {2}
    importer = HistoryImporter(
        messages=messages,
        users=FakeUsers(),
        embeddings=FakeEmbeddings(),
        vector_store=FakeVectorStore(),
        unit_of_work=FakeUow(),
        batch_size=10,
    )
    imported, skipped = await importer.import_messages(
        [_parsed(1), _parsed(2)],
        embed=False,
    )
    assert imported == 1
    assert skipped == 1
