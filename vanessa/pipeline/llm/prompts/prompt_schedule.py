"""Compose directive for a schedule request (posts Vanessa schedules herself).

The Retrieve stage applies the request and renders ``schedule_note`` from
``config/behavior/schedule/schedule.yaml``; here it only becomes a part.
"""

from vanessa.pipeline.llm.prompts.budget import PRIORITY_DIRECTIVES, BudgetPart


def schedule_parts(schedule_note: str | None) -> list[BudgetPart]:
    note = (schedule_note or "").strip()
    if not note:
        return []
    return [(PRIORITY_DIRECTIVES, "directives", note)]
