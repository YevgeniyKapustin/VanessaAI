"""Inbox-note task handler: vault write and optional broker reply."""

from __future__ import annotations

from vanessa.config import settings
from vanessa.contracts.messages import InboxNoteReply, TaskMessage
from vanessa.knowledge.inbox import InboxNoteError, save_inbox_note


class InboxNoteHandler:
    def __init__(self, vault, broker) -> None:
        self._vault = vault
        self._broker = broker

    async def handle(self, task: TaskMessage) -> None:
        payload = task.payload
        raw_attachment = payload.get("attachment_base64")
        try:
            path = await save_inbox_note(
                self._vault,
                text=str(payload.get("text") or ""),
                attachment_base64=(
                    str(raw_attachment) if raw_attachment else None
                ),
                attachment_suffix=str(payload.get("attachment_suffix") or ".jpg"),
            )
            reply = InboxNoteReply(
                correlation_id=task.correlation_id,
                ok=True,
                path=path,
            )
        except InboxNoteError as exc:
            reply = InboxNoteReply(
                correlation_id=task.correlation_id,
                ok=False,
                error=exc.code,
            )
        if task.reply_to and self._broker is not None:
            await self._broker.publish(
                task.reply_to, reply, ttl_seconds=settings.broker_reply_ttl_seconds
            )
