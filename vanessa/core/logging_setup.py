from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from vanessa.core.request_context import get_request_id

_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "aiogram.event",
    "aiogram.dispatcher",
    "huggingface_hub",
    "sentence_transformers",
)

_configured_service: str | None = None


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
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service
        return True


class LoguruStyleFormatter(logging.Formatter):
    def __init__(self, *, colorize: bool | None = None) -> None:
        super().__init__()
        if colorize is None:
            colorize = sys.stdout.isatty()
        self._colorize = colorize

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

    def format(self, record: logging.LogRecord) -> str:
        time_text = self.formatTime(record)
        level = record.levelname
        level_color = _Ansi.LEVEL.get(level, _Ansi.RESET)
        service = getattr(record, "service", "-")
        request_id = getattr(record, "request_id", "-")
        location = (
            f"{self._short_name(record.name)}:"
            f"{record.funcName}:{record.lineno}"
        )
        message = record.getMessage()

        # Mirror the stdlib Formatter: append the exception traceback so
        # ``logger.exception(...)`` lines actually surface the root cause
        # (without this, exceptions were logged but the traceback was dropped).
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            message = f"{message}\n{record.exc_text}"

        if self._colorize:
            sep = self._paint(" | ", _Ansi.DIM)
            time_part = self._paint(time_text, _Ansi.GREEN)
            level_part = self._paint(f"{level:<8}", level_color)
            scope_part = self._paint(f"{service}:{request_id}", _Ansi.CYAN)
            location_part = self._paint(location, _Ansi.CYAN)
            if level in {"ERROR", "CRITICAL"}:
                message_part = self._paint(message, level_color)
            elif level == "WARNING":
                message_part = self._paint(message, _Ansi.YELLOW)
            else:
                message_part = message
            return (
                f"{time_part}{sep}{level_part}{sep}"
                f"{scope_part}{sep}{location_part}{sep}{message_part}"
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

    def formatTime(
        self,
        record: logging.LogRecord,
        datefmt: str | None = None,
    ) -> str:
        del datefmt
        created = datetime.fromtimestamp(record.created, tz=UTC)
        return created.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def format(self, record: logging.LogRecord) -> str:
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
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
        for key, value in record.__dict__.items():
            if key in self._SKIP or key.startswith("_"):
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def _enable_windows_ansi() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except (AttributeError, OSError):
        return


def create_file_handler(
    service: str,
    level: str,
    log_dir: Path,
    *,
    max_bytes: int,
    backup_count: int,
    formatter: logging.Formatter | None = None,
) -> logging.Handler:
    """Build a rotating file handler writing plain (uncolored) log lines."""
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_dir / f"{service}.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.addFilter(RequestIdFilter())
    handler.addFilter(ServiceNameFilter(service))
    handler.setFormatter(formatter or LoguruStyleFormatter(colorize=False))
    return handler


def configure_logging(
    service: str,
    level: str | None = None,
) -> None:
    global _configured_service
    if _configured_service is not None:
        return

    from vanessa.config import settings

    _enable_windows_ansi()
    log_level = (level or settings.log_level).upper()
    formatter: logging.Formatter
    if settings.log_json:
        formatter = JsonFormatter()
    else:
        formatter = LoguruStyleFormatter()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.addFilter(ServiceNameFilter(service))
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    if settings.log_file_enabled:
        file_level = (settings.log_file_level or settings.log_level).upper()
        file_formatter: logging.Formatter = (
            JsonFormatter() if settings.log_json
            else LoguruStyleFormatter(colorize=False)
        )
        try:
            root.addHandler(
                create_file_handler(
                    service,
                    file_level,
                    Path(settings.log_dir),
                    max_bytes=settings.log_file_max_bytes,
                    backup_count=settings.log_file_backup_count,
                    formatter=file_formatter,
                )
            )
        except OSError:
            logging.getLogger(__name__).exception(
                "failed to open log file at %s, continuing without file logging",
                settings.log_dir,
            )

    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    _configured_service = service
