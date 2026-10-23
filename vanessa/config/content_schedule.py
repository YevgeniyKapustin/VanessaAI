"""Scheduled-post prompts: ``config/behavior/schedule/schedule.yaml``.

Kept apart from ``AppContent``: the agent needs the compose notes and the
worker needs the fire-time task; nothing else reads them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from vanessa.config.content import resolve_content_source

SCHEDULE_FILE = Path("schedule", "schedule.yaml")


class ScheduleContent(BaseModel):
    item: str = Field(min_length=1)
    when_cron: str = Field(min_length=1)
    when_once: str = Field(min_length=1)
    added_note: str
    listed_note: str
    empty_note: str
    cancelled_note: str
    not_found_note: str
    ambiguous_note: str
    rejected_note: str
    error_note: str
    reasons: dict[str, str] = Field(default_factory=dict)
    fire_task: str
    # null or 0 = off: max_tokens is not sent.
    max_tokens: int | None = Field(default=512, ge=0, le=4096)


def load_schedule_content(path: Path) -> ScheduleContent:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return ScheduleContent.model_validate(raw)


@lru_cache
def get_schedule_content() -> ScheduleContent:
    """Load the prompts. Fails loudly when the file is missing."""
    return load_schedule_content(resolve_content_source() / SCHEDULE_FILE)


__all__ = [
    "SCHEDULE_FILE",
    "ScheduleContent",
    "get_schedule_content",
    "load_schedule_content",
]
