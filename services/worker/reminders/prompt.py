"""Fire-time prompt for a scheduled post: the stored text as data + the task."""

from __future__ import annotations

import re

from vanessa.config.content_schedule import ScheduleContent

_TAG = "scheduled_post"
# The data block must not close itself early: strip our own tag from the text.
_TAG_RE = re.compile(r"<\s*/?\s*" + _TAG + r"\s*>", re.IGNORECASE)


def build_fire_user_prompt(text: str, prompts: ScheduleContent) -> str:
    body = _TAG_RE.sub("", text).strip()
    return f"<{_TAG}>\n{body}\n</{_TAG}>\n\n{prompts.fire_task.strip()}"


__all__ = ["build_fire_user_prompt"]
