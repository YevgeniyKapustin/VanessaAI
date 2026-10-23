from dataclasses import dataclass
from typing import Any

SCHEDULE_ACTIONS = frozenset({"add", "list", "cancel"})


@dataclass(frozen=True, slots=True)
class ScheduleRequest:
    """Planner output: add, list or cancel a post Vanessa schedules for herself.

    ``cron`` is a 5-field cron in the schedule timezone (recurring post);
    ``at`` is a local ``YYYY-MM-DDTHH:MM`` (one-shot post). ``text`` is the
    post to send; ``target`` names what to cancel (words, an id, or "all").
    """

    action: str
    cron: str = ""
    at: str = ""
    text: str = ""
    target: str = ""

    def to_trace_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "cron": self.cron,
            "at": self.at,
            "text": self.text,
            "target": self.target,
        }


__all__ = ["SCHEDULE_ACTIONS", "ScheduleRequest"]
