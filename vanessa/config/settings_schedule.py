"""Settings for posts Vanessa schedules for herself (reminders)."""

from __future__ import annotations


class ScheduleMixin:
    """Agent (add/list/cancel) and worker (firing) settings for reminders."""

    schedule_enabled: bool = True
    # IANA zone of the chat: cron fields, "tomorrow at 10" style times and
    # every time label Vanessa sees (storage stays UTC).
    schedule_timezone: str = "Asia/Tbilisi"
    schedule_max_per_chat: int = 20
    # A recurring schedule may not fire more often than this.
    schedule_min_interval_minutes: int = 30
    # Worker checks the table for due posts this often.
    schedule_poll_seconds: float = 30.0
    # A post more late than this (worker was down) is skipped, not sent.
    schedule_max_late_minutes: int = 180
    schedule_text_max_chars: int = 1000
    # Retell the stored text in persona at fire time (plain text on failure).
    schedule_rephrase_enabled: bool = True
