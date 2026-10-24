"""Append-only JSON-lines file with size rotation (one file per process).

Each service writes its own file: two processes that rotate one file would
rename it under each other.
"""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class _OnceHandler(RotatingFileHandler):
    """Report the first write error as one warning, then stay quiet."""

    failed = False

    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802
        del record
        if self.failed:
            return
        self.failed = True
        logger.warning(
            "trace_log_write_failed path=%s", self.baseFilename, exc_info=sys.exc_info()
        )


class TraceLogWriter:
    """Writes one JSON object per line; thread-safe through the handler lock."""

    def __init__(self, path: Path, *, max_bytes: int, backup_count: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._handler = _OnceHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )

    def write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, default=str)
        self._handler.handle(logging.makeLogRecord({"msg": line}))

    def close(self) -> None:
        self._handler.close()
