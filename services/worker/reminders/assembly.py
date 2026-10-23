"""Build the scheduled-post loop (None when the skill is off)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from services.worker.hermes.assembly import followup_model
from services.worker.hermes.prompt import build_followup_system_prompt
from services.worker.reminders.compose import ReminderComposer
from services.worker.reminders.scheduler import ReminderScheduler
from vanessa.config.content import AppContent, get_content
from vanessa.config.content_schedule import ScheduleContent, get_schedule_content
from vanessa.infrastructure.db.session import async_session_factory
from vanessa.llm.completers import create_chat_completer
from vanessa.pipeline.schedule.timing import schedule_zone

_CHANNEL = "telegram"


def build_reminder_composer(
    settings, content: AppContent, prompts: ScheduleContent
) -> ReminderComposer:
    generation = replace(
        content.llm.generation.composer.to_params(), max_tokens=prompts.max_tokens
    )
    completer = create_chat_completer() if settings.schedule_rephrase_enabled else None
    return ReminderComposer(
        completer,
        model=followup_model(settings),
        system_prompt=build_followup_system_prompt(content, _CHANNEL),
        prompts=prompts,
        generation=generation,
    )


def build_reminder_scheduler(
    broker, *, outbound_stream: str, settings, session_factory=None
) -> ReminderScheduler | None:
    """The loop, or None when the skill is off or there is nowhere to post."""
    if not settings.schedule_enabled or broker is None or not outbound_stream:
        return None
    composer = build_reminder_composer(settings, get_content(), get_schedule_content())
    return ReminderScheduler(
        session_factory or async_session_factory,
        broker,
        composer,
        outbound_stream=outbound_stream,
        tz=schedule_zone(settings.schedule_timezone),
        poll_seconds=settings.schedule_poll_seconds,
        max_late=timedelta(minutes=settings.schedule_max_late_minutes),
    )


__all__ = ["build_reminder_composer", "build_reminder_scheduler"]
