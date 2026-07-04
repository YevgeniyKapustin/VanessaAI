from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import ClassVar, Literal

from app.core.request_context import get_request_id

ServiceName = Literal["api", "bot", "import"]

_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "aiogram.event",
    "aiogram.dispatcher",
    "huggingface_hub",
    "sentence_transformers",
)

_configured_service: ServiceName | None = None


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
    def __init__(self, service: ServiceName) -> None:
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
        created = datetime.fromtimestamp(record.created)
        return (
            f"{created.strftime('%Y-%m-%d %H:%M:%S')}"
            f".{int(record.msecs):03d}"
        )

    @staticmethod
    def _short_name(name: str) -> str:
        if name.startswith("app."):
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


def configure_logging(
    service: ServiceName,
    level: str | None = None,
) -> None:
    global _configured_service
    if _configured_service is not None:
        return

    from app.config import settings

    _enable_windows_ansi()
    log_level = (level or settings.log_level).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.addFilter(ServiceNameFilter(service))
    handler.setFormatter(LoguruStyleFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    _configured_service = service
