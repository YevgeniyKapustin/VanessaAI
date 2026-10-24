"""Opt-in per-turn trace log: ``<LOG_DIR>/trace-<service>.jsonl``.

One JSON record per step (planner, retrieve, compose, worker jobs), keyed by
the turn ``request_id`` and ``chat_id`` from ``vanessa.core.request_context``.
Off unless ``TRACE_LOG_ENABLED=true`` and the process root calls
``configure_trace_log``. Tracing never breaks a turn: a failed write logs
one warning and the turn goes on. The file holds private chat text.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vanessa.config.settings import settings
from vanessa.core.request_context import get_chat_id, get_request_id
from vanessa.infrastructure.observability.trace_log.clip import clip_text, jsonable
from vanessa.infrastructure.observability.trace_log.writer import TraceLogWriter

logger = logging.getLogger(__name__)


class _TraceState:
    writer: TraceLogWriter | None = None
    service: str = "-"
    failed: bool = False


def trace_log_path(service: str) -> Path:
    return Path(settings.log_dir) / f"trace-{service}.jsonl"


def configure_trace_log(service: str) -> None:
    """Open the trace file of this process when ``TRACE_LOG_ENABLED``."""
    if not settings.trace_log_enabled:
        return
    path = trace_log_path(service)
    try:
        writer = TraceLogWriter(
            path,
            max_bytes=settings.trace_log_max_bytes,
            backup_count=settings.trace_log_backup_count,
        )
    except OSError:
        logger.warning("trace_log_open_failed path=%s", path, exc_info=True)
        return
    set_trace_writer(writer, service)
    logger.info("trace_log_enabled path=%s", path)


def set_trace_writer(writer: TraceLogWriter | None, service: str = "-") -> None:
    """Install (or drop, with ``None``) the writer; tests use it directly."""
    _TraceState.writer = writer
    _TraceState.service = service
    _TraceState.failed = False


def trace_enabled() -> bool:
    return _TraceState.writer is not None


def trace_event(stage: str, **fields: Any) -> None:
    """Append one record for ``stage``; a no-op when tracing is off."""
    writer = _TraceState.writer
    if writer is None:
        return
    try:
        writer.write(_record(stage, fields))
    except Exception as exc:  # noqa: BLE001 - tracing must never break a turn
        report_trace_failure(exc)


def report_trace_failure(exc: Exception) -> None:
    """Log the first failed record with its traceback; later ones are silent."""
    if _TraceState.failed:
        return
    _TraceState.failed = True
    logger.warning("trace_log_record_failed", exc_info=exc)


def _record(stage: str, fields: dict[str, Any]) -> dict[str, Any]:
    head = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "service": _TraceState.service,
        "request_id": get_request_id(),
        "chat_id": get_chat_id(),
        "stage": stage,
    }
    body = jsonable(fields, settings.trace_log_max_field_chars)
    return {**head, **{key: value for key, value in body.items() if key not in head}}


__all__ = [
    "TraceLogWriter",
    "clip_text",
    "configure_trace_log",
    "report_trace_failure",
    "set_trace_writer",
    "trace_enabled",
    "trace_event",
    "trace_log_path",
]
