"""Reaction task handler: store a chat reaction in the session history."""

from __future__ import annotations

import logging

from vanessa.contracts.messages import TaskMessage
from vanessa.infrastructure.db import repository

logger = logging.getLogger(__name__)

#: ``messages.role`` of a stored reaction row (never a chat message).
REACTION_ROLE = "reaction"


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class ReactionHandler:
    """Writes one reaction as a ``reaction`` row in the chat's channel.

    The row carries the reacted-to message id, so the prompt can show which
    message the emoji belongs to (``<reaction ... to="17"/>``). Removal updates
    (an empty reaction set) never reach this handler.
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def handle(self, task: TaskMessage) -> None:
        payload = task.payload or {}
        chat_id = _int_or_none(payload.get("telegram_chat_id"))
        message_id = _int_or_none(payload.get("message_id"))
        emoji = str(payload.get("emoji") or "").strip()
        if chat_id is None or message_id is None or not emoji:
            logger.info("reaction_task_skipped payload=%s", sorted(payload))
            return
        channel = f"telegram:{chat_id}"
        async with self._session_factory() as session:
            repo = repository.MessageRepository(session)
            target_id = await repo.get_id_by_telegram_message_id(
                message_id,
                channel=channel,
            )
            await repo.create(
                role=REACTION_ROLE,
                content=emoji,
                sender_telegram_id=_int_or_none(payload.get("user_id")),
                sender_display_name=str(payload.get("user_name") or "") or None,
                telegram_message_id=message_id,
                reply_to_message_id=target_id,
                channel=channel,
            )
            await session.commit()
        logger.info(
            "reaction_stored chat_id=%s message_id=%s emoji=%s target=%s",
            chat_id,
            message_id,
            emoji,
            target_id,
        )
