from types import SimpleNamespace
from typing import ClassVar, Self
from unittest.mock import AsyncMock

from services.worker.handlers.knowledge import (
    MemoryExtractHandler,
    MetricsSnapshotHandler,
)
from services.worker.handlers.photo import PhotoCaptionHandler
from vanessa.contracts.messages import TaskKind, TaskMessage
from vanessa.core.messages import ContextMessage, context_message_to_payload
from vanessa.infrastructure.db import repository

_CHAT_ID = 5


class _Session:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def commit(self) -> None:
        return None


class _CaptionRepo:
    updated: ClassVar[list[tuple[int, str]]] = []

    def __init__(self, session) -> None:
        del session

    async def get_by_id(self, message_id: int):
        del message_id
        return SimpleNamespace(
            attachments=[{"data_url": "data:image/jpeg;base64,AA"}]
        )

    async def update_photo_caption(self, message_id: int, caption: str) -> None:
        self.updated.append((message_id, caption))


class _Captioner:
    async def generate(self, image) -> str:
        del image
        return "a cat"


class _SkipRepo:
    def __init__(self, session) -> None:
        del session

    async def get_by_id(self, message_id: int):
        del message_id
        return SimpleNamespace(attachments=[{"mime": "image/jpeg"}])


async def test_photo_caption_handler(monkeypatch) -> None:
    _CaptionRepo.updated = []
    monkeypatch.setattr(repository, "MessageRepository", _CaptionRepo)
    handler = PhotoCaptionHandler(_Captioner(), _Session)
    await handler.handle(TaskMessage(task=TaskKind.PHOTO_CAPTION, payload={}))
    await handler.handle(
        TaskMessage(task=TaskKind.PHOTO_CAPTION, payload={"message_id": 4})
    )
    assert _CaptionRepo.updated == [(4, "a cat")]


async def test_photo_caption_skips_without_attachment(monkeypatch) -> None:
    monkeypatch.setattr(repository, "MessageRepository", _SkipRepo)
    handler = PhotoCaptionHandler(AsyncMock(), _Session)
    await handler.handle(
        TaskMessage(task=TaskKind.PHOTO_CAPTION, payload={"message_id": 1})
    )


async def test_memory_extract_handler() -> None:
    memory_calls: list[dict] = []

    class Memory:
        async def run(self, **kwargs) -> int:
            memory_calls.append(kwargs)
            return 1

    payload = {
        "telegram_chat_id": _CHAT_ID,
        "source_message_ids": [1],
        "messages": [
            context_message_to_payload(
                ContextMessage(id=1, role="user", content="hi")
            ),
            "skip",
        ],
    }
    await MemoryExtractHandler(Memory()).handle(
        TaskMessage(task=TaskKind.MEMORY_EXTRACT, payload=payload)
    )
    assert memory_calls[0]["telegram_chat_id"] == _CHAT_ID


async def test_metrics_snapshot_handler(monkeypatch) -> None:
    metrics_calls: list = []

    class Metrics:
        async def run(self, _repo, **kwargs) -> int:
            metrics_calls.append(kwargs)
            return 1

    monkeypatch.setattr(repository, "MessageRepository", lambda _s: object())
    await MetricsSnapshotHandler(Metrics(), _Session).handle(
        TaskMessage(
            task=TaskKind.METRICS_SNAPSHOT,
            payload={"sender_telegram_id": 9},
        )
    )
    assert metrics_calls[0]["only_senders"] == {9}
