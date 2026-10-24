"""Shared fixture for trace-log tests: a writer into ``tmp_path``."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from vanessa.infrastructure.observability.trace_log import (
    TraceLogWriter,
    set_trace_writer,
)

type ReadTrace = Callable[[], list[dict]]


def read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


@pytest.fixture
def trace_records(tmp_path: Path) -> Iterator[ReadTrace]:
    """Install a trace writer; the fixture value reads the records back."""
    path = tmp_path / "trace-test.jsonl"
    writer = TraceLogWriter(path, max_bytes=10_000_000, backup_count=1)
    set_trace_writer(writer, "test")
    yield lambda: read_records(path)
    set_trace_writer(None)
    writer.close()
