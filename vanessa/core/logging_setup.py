from __future__ import annotations

import ctypes
import logging
import logging.handlers
import sys
from pathlib import Path

from vanessa.config import settings
from vanessa.core.logging_formatters import (
    JsonFormatter,
    LoguruStyleFormatter,
    RequestIdFilter,
    ServiceName,
    ServiceNameFilter,
)

_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "aiogram.event",
    "aiogram.dispatcher",
    "huggingface_hub",
    "sentence_transformers",
)

_configured_service_name: ServiceName | None = None


def _enable_windows_ansi() -> None:
    if sys.platform != "win32":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except (AttributeError, OSError):
        return


def create_file_handler(
    service_name: ServiceName,
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
        log_dir / f"{service_name}.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.addFilter(RequestIdFilter())
    handler.addFilter(ServiceNameFilter(service_name))
    handler.setFormatter(formatter or LoguruStyleFormatter(colorize=False))
    return handler


def _console_formatter() -> logging.Formatter:
    if settings.log_json:
        return JsonFormatter()
    return LoguruStyleFormatter()


def _file_log_formatter() -> logging.Formatter:
    if settings.log_json:
        return JsonFormatter()
    return LoguruStyleFormatter(colorize=False)


def _attach_file_handler(
    root: logging.Logger,
    service_name: ServiceName,
) -> None:
    if not settings.log_file_enabled:
        return
    file_level = (settings.log_file_level or settings.log_level).upper()
    try:
        root.addHandler(
            create_file_handler(
                service_name,
                file_level,
                Path(settings.log_dir),
                max_bytes=settings.log_file_max_bytes,
                backup_count=settings.log_file_backup_count,
                formatter=_file_log_formatter(),
            )
        )
    except OSError:
        logging.getLogger(__name__).exception(
            "failed to open log file at %s, continuing without file logging",
            settings.log_dir,
        )


def configure_logging(
    service_name: ServiceName,
    level: str | None = None,
) -> None:
    global _configured_service_name  # noqa: PLW0603 - tests reset this module flag
    if _configured_service_name is not None:
        return

    _enable_windows_ansi()
    log_level = (level or settings.log_level).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.addFilter(ServiceNameFilter(service_name))
    handler.setFormatter(_console_formatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    _attach_file_handler(root, service_name)

    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    _configured_service_name = service_name
