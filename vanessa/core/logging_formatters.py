from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import ClassVar, override

from vanessa.core.logging_format_text import (
    ensure_exc_text,
    extra_log_fields,
    message_with_exc,
)
from vanessa.core.request_context import get_request_id

type ServiceName = str


class _Ansi:
    RESET = "\033[0m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    CYAN = "\033[36m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BOLD_RED = "\033[1;31m"

    LEVEL: ClassVar[dict[str, str]] = {
        "DEBUG": CYAN,
        "INFO": GREEN,
        "WARNING": YELLOW,
        "ERROR": RED,
        "CRITICAL": BOLD_RED,
    }


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class ServiceNameFilter(logging.Filter):
    def __init__(self, service_name: ServiceName) -> None:
        super().__init__()
        self._service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service_name
        return True


class LoguruStyleFormatter(logging.Formatter):
    def __init__(self, *, colorize: bool | None = None) -> None:
        super().__init__()
        if colorize is None:
            colorize = sys.stdout.isatty()
        self._colorize = colorize

    @override
    def formatTime(
        self,
        record: logging.LogRecord,
        datefmt: str | None = None,
    ) -> str:
        del datefmt
        created = datetime.fromtimestamp(record.created, tz=UTC)
        return (
            f"{created.strftime('%Y-%m-%d %H:%M:%S')}"
            f".{int(record.msecs):03d}"
        )

    @staticmethod
    def _short_name(name: str) -> str:
        if name.startswith("vanessa."):
            return name[4:]
        return name

    def _paint(self, text: str, color: str) -> str:
        if not self._colorize:
            return text
        return f"{color}{text}{_Ansi.RESET}"

    def _paint_message(self, message: str, level: str, level_color: str) -> str:
        if level in {"ERROR", "CRITICAL"}:
            return self._paint(message, level_color)
        if level == "WARNING":
            return self._paint(message, _Ansi.YELLOW)
        return message

    def _format_colorized(
        self,
        time_text: str,
        level: str,
        service: str,
        request_id: str,
        location: str,
        message: str,
    ) -> str:
        level_color = _Ansi.LEVEL.get(level, _Ansi.RESET)
        sep = self._paint(" | ", _Ansi.DIM)
        time_part = self._paint(time_text, _Ansi.GREEN)
        level_part = self._paint(f"{level:<8}", level_color)
        scope_part = self._paint(f"{service}:{request_id}", _Ansi.CYAN)
        location_part = self._paint(location, _Ansi.CYAN)
        message_part = self._paint_message(message, level, level_color)
        return (
            f"{time_part}{sep}{level_part}{sep}"
            f"{scope_part}{sep}{location_part}{sep}{message_part}"
        )

    def format(self, record: logging.LogRecord) -> str:
        time_text = self.formatTime(record)
        level = record.levelname
        service = getattr(record, "service", "-")
        request_id = getattr(record, "request_id", "-")
        location = (
            f"{self._short_name(record.name)}:"
            f"{record.funcName}:{record.lineno}"
        )
        message = message_with_exc(self, record)
        if self._colorize:
            return self._format_colorized(
                time_text, level, service, request_id, location, message
            )
        return (
            f"{time_text} | {level:<8} | {service}:{request_id} | "
            f"{location} | {message}"
        )


class JsonFormatter(logging.Formatter):
    """One JSON object per line for Vector / Loki / Elasticsearch."""

    _SKIP = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "taskName",
            "request_id",
            "service",
        }
    )

    @override
    def formatTime(
        self,
        record: logging.LogRecord,
        datefmt: str | None = None,
    ) -> str:
        del datefmt
        created = datetime.fromtimestamp(record.created, tz=UTC)
        return created.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def format(self, record: logging.LogRecord) -> str:
        ensure_exc_text(self, record)
        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "service": getattr(record, "service", "-"),
            "request_id": getattr(record, "request_id", "-"),
            "logger": record.name,
            "func": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        if record.exc_text:
            payload["exception"] = record.exc_text
        payload.update(extra_log_fields(record, self._SKIP))
        return json.dumps(payload, ensure_ascii=False, default=str)
