"""Save what the adapter posted on its own as Vanessa's messages.

A late follow-up (Hermes, a reminder) goes from the worker straight to the
adapter. The adapter then sends ``PostedMessages`` on the ``turns`` stream.
Each text becomes one ``assistant`` row at the time it went out, so the
next turn sees the follow-up in the chat history, in order. A posted
lookup result is also noted in ``RecentAnswers``.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from vanessa.contracts.posted import PostedMessages
from vanessa.core.hermes_answers import RecentAnswers
from vanessa.infrastructure.db.repository import MessageRepository

logger = logging.getLogger(__name__)

#: Gap between the rows of one follow-up, so they keep their order.
PART_STEP = timedelta(milliseconds=1)


class PostedRecorder:
    def __init__(
        self,
        session_factory,
        answers: RecentAnswers | None = None,
        repository=MessageRepository,
    ) -> None:
        self._session_factory = session_factory
        self._answers = answers
        self._repository = repository

    async def record(self, posted: PostedMessages) -> None:
        async with self._session_factory() as session:
            await self._save(self._repository(session), posted)
            await session.commit()
        if self._answers is not None and posted.question:
            self._answers.note(posted.telegram_chat_id, posted.question)
        logger.info(
            "posted_saved chat_id=%s source=%s messages=%s",
            posted.telegram_chat_id,
            posted.source,
            len(posted.texts),
        )

    async def _save(self, messages, posted: PostedMessages) -> None:
        for index, text in enumerate(posted.texts):
            await messages.create(
                role="assistant",
                content=text,
                created_at=posted.posted_at + index * PART_STEP,
                reply_to_message_id=posted.reply_to_message_id if index == 0 else None,
                channel=posted.channel,
            )
