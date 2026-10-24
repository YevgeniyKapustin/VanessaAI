"""Settings for the per-turn trace log (JSON lines, one record per step)."""

from __future__ import annotations


class TraceLogMixin:
    """Opt-in debug trace of planner / retrieve / compose / worker steps.

    The file holds private chat text: keep it on the server.
    """

    trace_log_enabled: bool = False
    # Rotation per service file (``<LOG_DIR>/trace-<service>.jsonl``).
    trace_log_max_bytes: int = 20_971_520  # 20 MiB
    trace_log_backup_count: int = 5
    # Cap for one string field (a prompt, an output); longer text is clipped.
    trace_log_max_field_chars: int = 40_000
    # Cap for ``reasoning_content`` (thinking mode): it is long and rarely needed.
    trace_log_max_reasoning_chars: int = 4_000
