"""Parse the planner ``schedule`` object into a ``ScheduleRequest``.

Only the shape is checked here. Timing rules (cron syntax, past dates,
frequency) live in ``vanessa.pipeline.schedule`` and run in Retrieve.
"""

from __future__ import annotations

from vanessa.config.settings import settings
from vanessa.pipeline.decision.schedule_request import ScheduleRequest

_CRON_MAX_CHARS = 64
_AT_MAX_CHARS = 32
_TARGET_MAX_CHARS = 200


def _field(payload: dict, key: str, limit: int) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    return str(value).strip()[:limit].strip()


def _add_request(raw: dict) -> ScheduleRequest | None:
    text = _field(raw, "text", settings.schedule_text_max_chars)
    cron = _field(raw, "cron", _CRON_MAX_CHARS)
    at = _field(raw, "at", _AT_MAX_CHARS)
    if not text or not (cron or at):
        return None
    # A cron wins over a date: one schedule per post.
    return ScheduleRequest(action="add", cron=cron, at="" if cron else at, text=text)


def _list_request(_raw: dict) -> ScheduleRequest:
    return ScheduleRequest(action="list")


def _cancel_request(raw: dict) -> ScheduleRequest:
    # Empty target: the actions layer cancels only when the chat has one post.
    target = _field(raw, "target", _TARGET_MAX_CHARS)
    return ScheduleRequest(action="cancel", target=target)


_BUILDERS = {"add": _add_request, "list": _list_request, "cancel": _cancel_request}


def parse_schedule(payload: dict) -> ScheduleRequest | None:
    """Return the request, or None when absent, unknown or incomplete."""
    raw = payload.get("schedule")
    if not isinstance(raw, dict):
        return None
    action = str(raw.get("action", "")).strip().lower()
    builder = _BUILDERS.get(action)
    return builder(raw) if builder is not None else None


__all__ = ["parse_schedule"]
