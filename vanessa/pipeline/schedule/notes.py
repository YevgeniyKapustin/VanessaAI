"""Compose directive that tells Vanessa what happened to a schedule request."""

from __future__ import annotations

from vanessa.config.content_schedule import ScheduleContent
from vanessa.core.reminders import Reminder
from vanessa.pipeline.schedule.actions import ScheduleOutcome
from vanessa.pipeline.schedule.timing import SchedulePolicy, format_local

_SECONDS_PER_MINUTE = 60


def describe_when(
    reminder: Reminder, content: ScheduleContent, policy: SchedulePolicy
) -> str:
    moment = format_local(reminder.next_run_at, policy.tz)
    if reminder.is_once:
        return content.when_once.format(next=moment)
    return content.when_cron.format(cron=reminder.cron, next=moment)


def render_items(
    reminders: tuple[Reminder, ...],
    content: ScheduleContent,
    policy: SchedulePolicy,
) -> str:
    lines = [
        content.item.format(
            number=number,
            when=describe_when(reminder, content, policy),
            text=reminder.text,
        )
        for number, reminder in enumerate(reminders, start=1)
    ]
    return "\n".join(lines)


def _reason(detail: str, content: ScheduleContent, policy: SchedulePolicy) -> str:
    template = content.reasons.get(detail) or detail or "?"
    minutes = int(policy.min_interval.total_seconds() // _SECONDS_PER_MINUTE)
    return template.format(min_minutes=minutes, max_per_chat=policy.max_per_chat)


def _added(
    outcome: ScheduleOutcome, content: ScheduleContent, policy: SchedulePolicy
) -> str:
    reminder = outcome.reminders[0]
    return content.added_note.format(
        when=describe_when(reminder, content, policy), text=reminder.text
    )


def _rejected(
    outcome: ScheduleOutcome, content: ScheduleContent, policy: SchedulePolicy
) -> str:
    return content.rejected_note.format(reason=_reason(outcome.detail, content, policy))


def _listing(template: str):
    def render(
        outcome: ScheduleOutcome, content: ScheduleContent, policy: SchedulePolicy
    ) -> str:
        note = getattr(content, template)
        return note.format(items=render_items(outcome.reminders, content, policy))

    return render


def _fixed(template: str):
    def render(
        _outcome: ScheduleOutcome, content: ScheduleContent, _policy: SchedulePolicy
    ) -> str:
        return getattr(content, template)

    return render


_RENDERERS = {
    "added": _added,
    "rejected": _rejected,
    "listed": _listing("listed_note"),
    "cancelled": _listing("cancelled_note"),
    "not_found": _listing("not_found_note"),
    "ambiguous": _listing("ambiguous_note"),
    "empty": _fixed("empty_note"),
}


def render_note(
    outcome: ScheduleOutcome, content: ScheduleContent, policy: SchedulePolicy
) -> str:
    """Directive text for compose; unknown status → the error note."""
    renderer = _RENDERERS.get(outcome.status, _fixed("error_note"))
    return renderer(outcome, content, policy).strip()


__all__ = ["describe_when", "render_items", "render_note"]
