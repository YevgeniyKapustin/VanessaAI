"""Turn a stored scheduled post into the chat text, in Vanessa's persona.

The LLM retells the post in her voice. Any failure, an empty answer, or a
changed / lost link falls back to the stored text as is, so the link always
reaches the chat unchanged.
"""

from __future__ import annotations

import logging

from services.worker.hermes.compose import chat_request, final_text, truncate_message
from services.worker.reminders.prompt import build_fire_user_prompt
from vanessa.config.content_schedule import ScheduleContent
from vanessa.core.protocols import LLMChatCompleter
from vanessa.core.reminders import Reminder
from vanessa.llm.generation import LLMGenerationParams
from vanessa.pipeline.llm.format.answer_tag import is_untagged_reply
from vanessa.pipeline.llm.tagged_reply import request_tagged
from vanessa.pipeline.schedule.urls import extract_urls, urls_intact

logger = logging.getLogger(__name__)

LLM_KIND = "reminder_post"


class ReminderComposer:
    """LLM boundary for scheduled posts (completer + persona prompt)."""

    def __init__(
        self,
        completer: LLMChatCompleter | None,
        *,
        model: str,
        system_prompt: str,
        prompts: ScheduleContent,
        generation: LLMGenerationParams,
    ) -> None:
        # completer=None turns the retelling off: the stored text is posted.
        self._completer = completer
        self._model = model
        self._system = system_prompt
        self._prompts = prompts
        self._generation = generation

    async def compose(self, reminder: Reminder) -> str:
        """Always return a non-empty text of at most 4096 characters."""
        fallback = truncate_message(reminder.text)
        if self._completer is None:
            return fallback
        text = truncate_message(await self._retell(reminder))
        if not text or not urls_intact(text, extract_urls(reminder.text)):
            return fallback
        return text

    async def _retell(self, reminder: Reminder) -> str:
        try:
            raw = await self._complete(reminder.text)
        except Exception as exc:  # noqa: BLE001 - any LLM failure → stored text
            # The type only: provider errors may echo the prompt.
            logger.warning(
                "reminder_llm_failed reminder_id=%s error=%s",
                reminder.id,
                type(exc).__name__,
            )
            return ""
        if is_untagged_reply(raw):
            # Still no [answer] after the retry: bare reasoning → stored text.
            logger.warning(
                "reminder_llm_untagged reminder_id=%s chars=%s",
                reminder.id,
                len(raw),
            )
            return ""
        return final_text(raw)

    async def _complete(self, text: str) -> str:
        completer = self._completer
        assert completer is not None
        user = build_fire_user_prompt(text, self._prompts)
        messages, extra = chat_request(completer, self._system, user)
        return await request_tagged(
            lambda: completer.complete(
                self._model,
                messages,
                kind=LLM_KIND,
                **self._generation.to_llm_kwargs(),
                **extra,
            ),
            str,
            model=self._model,
        )


__all__ = ["LLM_KIND", "ReminderComposer"]
