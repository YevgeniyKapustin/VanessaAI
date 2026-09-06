from __future__ import annotations

import logging


def ensure_exc_text(
    formatter: logging.Formatter,
    record: logging.LogRecord,
) -> None:
    if record.exc_info and not record.exc_text:
        record.exc_text = formatter.formatException(record.exc_info)


def message_with_exc(
    formatter: logging.Formatter,
    record: logging.LogRecord,
) -> str:
    # Mirror the stdlib Formatter: append the exception traceback so
    # ``logger.exception(...)`` lines actually surface the root cause
    # (without this, exceptions were logged but the traceback was dropped).
    ensure_exc_text(formatter, record)
    message = record.getMessage()
    if not record.exc_text:
        return message
    return f"{message}\n{record.exc_text}"


def extra_log_fields(
    record: logging.LogRecord,
    skip: frozenset[str],
) -> dict[str, object]:
    extra: dict[str, object] = {}
    for key, value in record.__dict__.items():
        if key in skip or key.startswith("_"):
            continue
        extra[key] = value
    return extra
