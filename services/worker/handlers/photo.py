"""Photo-caption task handler."""

from __future__ import annotations

from vanessa.contracts.messages import TaskMessage
from vanessa.core.messages import ImageAttachment
from vanessa.infrastructure.db import repository


class PhotoCaptionHandler:
    def __init__(self, captioner, session_factory) -> None:
        self._captioner = captioner
        self._session_factory = session_factory

    async def handle(self, task: TaskMessage) -> None:
        message_id = int(task.payload.get("message_id") or 0)
        if not message_id:
            return
        async with self._session_factory() as session:
            await self._caption_message(session, message_id)

    async def _caption_message(self, session, message_id: int) -> None:
        repo = repository.MessageRepository(session)
        record = await repo.get_by_id(message_id)
        first = _first_photo_attachment(record)
        if first is None:
            return
        caption = await self._captioner.generate(
            ImageAttachment.from_dict(first)
        )
        if not caption:
            return
        await repo.update_photo_caption(message_id, caption)
        await session.commit()


def _first_photo_attachment(record) -> dict | None:
    if record is None:
        return None
    if not record.attachments:
        return None
    return _dict_with_data_url(record.attachments[0])


def _dict_with_data_url(first) -> dict | None:
    if not isinstance(first, dict):
        return None
    if not first.get("data_url"):
        return None
    return first
