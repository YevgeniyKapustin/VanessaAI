"""Apply a planner ``ScheduleRequest``: add, list or cancel a chat post."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from vanessa.core.protocols import ReminderStoreProtocol
from vanessa.core.reminders import NewReminder, Reminder
from vanessa.pipeline.decision.schedule_request import ScheduleRequest
from vanessa.pipeline.schedule.duplicates import find_duplicate
from vanessa.pipeline.schedule.matching import match_reminders
from vanessa.pipeline.schedule.timing import SchedulePolicy, first_run
from vanessa.pipeline.schedule.urls import keep_urls


@dataclass(frozen=True, slots=True)
class ScheduleCall:
    """One schedule request in one chat, with what is needed to apply it."""

    request: ScheduleRequest
    chat_id: int
    source_text: str
    now_utc: datetime
    policy: SchedulePolicy
    sender_id: int | None = None


@dataclass(frozen=True, slots=True)
class ScheduleOutcome:
    """``status``: added, exists, listed, empty, cancelled, not_found,
    ambiguous, rejected or error. ``detail`` is the reject reason code."""

    status: str
    reminders: tuple[Reminder, ...] = ()
    detail: str = ""


def _post_text(call: ScheduleCall) -> str:
    text = call.request.text[: call.policy.text_max_chars].strip()
    return keep_urls(text, call.source_text)


async def _add(call: ScheduleCall, store: ReminderStoreProtocol) -> ScheduleOutcome:
    run_at, reason = first_run(call.request, call.now_utc, call.policy)
    if run_at is None:
        return ScheduleOutcome("rejected", detail=reason)
    existing = await store.list_for_chat(call.chat_id)
    text = _post_text(call)
    same = find_duplicate(existing, cron=call.request.cron, run_at=run_at, text=text)
    if same is not None:
        return ScheduleOutcome("exists", (same,))
    if len(existing) >= call.policy.max_per_chat:
        return ScheduleOutcome("rejected", tuple(existing), detail="limit")
    reminder = await store.add(
        NewReminder(
            chat_id=call.chat_id,
            text=text,
            next_run_at=run_at,
            cron=call.request.cron,
            created_by=call.sender_id,
        )
    )
    return ScheduleOutcome("added", (reminder,))


async def _list(call: ScheduleCall, store: ReminderStoreProtocol) -> ScheduleOutcome:
    reminders = tuple(await store.list_for_chat(call.chat_id))
    return ScheduleOutcome("listed" if reminders else "empty", reminders)


async def _cancel(call: ScheduleCall, store: ReminderStoreProtocol) -> ScheduleOutcome:
    reminders = await store.list_for_chat(call.chat_id)
    if not reminders:
        return ScheduleOutcome("empty")
    picked = match_reminders(reminders, call.request.target)
    if picked is None:
        return ScheduleOutcome("ambiguous", tuple(reminders))
    if not picked:
        return ScheduleOutcome("not_found", tuple(reminders))
    await store.delete(call.chat_id, [reminder.id for reminder in picked])
    return ScheduleOutcome("cancelled", tuple(picked))


_Action = Callable[[ScheduleCall, ReminderStoreProtocol], Awaitable[ScheduleOutcome]]
_ACTIONS: dict[str, _Action] = {"add": _add, "list": _list, "cancel": _cancel}


async def apply_schedule(
    call: ScheduleCall, store: ReminderStoreProtocol
) -> ScheduleOutcome:
    action = _ACTIONS.get(call.request.action)
    if action is None:
        return ScheduleOutcome("rejected", detail="bad_action")
    return await action(call, store)


__all__ = ["ScheduleCall", "ScheduleOutcome", "apply_schedule"]
