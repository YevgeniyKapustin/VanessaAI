"""Trace log: writer, record head, clipping, disabled mode, failures."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from tests.trace_helpers import ReadTrace
from vanessa.config.settings import settings
from vanessa.core.request_context import chat_id_var, request_id_var
from vanessa.infrastructure.observability import trace_log
from vanessa.infrastructure.observability.trace_log import (
    TraceLogWriter,
    configure_trace_log,
    set_trace_writer,
    trace_enabled,
    trace_event,
)
from vanessa.infrastructure.observability.trace_log.clip import clip_text, jsonable

RECORDS = 10
SHORT_HEAD = 100
CHAT_ID = -5441986530


class _Mood(Enum):
    CALM = "calm"


@dataclass
class _Plan:
    should_reply: bool
    mood: _Mood


class _Model(BaseModel):
    name: str


def test_writer_appends_json_lines_and_rotates(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "trace-x.jsonl"
    writer = TraceLogWriter(path, max_bytes=200, backup_count=2)
    for index in range(RECORDS):
        writer.write({"n": index, "text": "привет" * 5})
    writer.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["n"] == RECORDS - 1
    assert "привет" in lines[-1]
    assert (tmp_path / "deep" / "trace-x.jsonl.1").exists()
    assert not (tmp_path / "deep" / "trace-x.jsonl.3").exists()


def test_clip_text_cuts_long_text_and_data_urls() -> None:
    assert clip_text("short", 10) == "short"
    assert clip_text("abcdefghij", 4) == "abcd…[+6 chars]"
    data_url = "data:image/jpeg;base64," + "A" * 500
    clipped = clip_text(data_url, 10_000)
    assert clipped.endswith(f"[data url, {len(data_url)} chars]")
    assert len(clipped) < SHORT_HEAD


def test_jsonable_handles_dataclass_enum_model_and_objects() -> None:
    value = {
        "plan": _Plan(should_reply=True, mood=_Mood.CALM),
        "model": _Model(name="vee"),
        "items": ("a" * 20, {1, 2}),
        "other": object(),
        3: None,
    }
    result = jsonable(value, 5)
    assert result["plan"] == {"should_reply": True, "mood": "calm"}
    assert result["model"] == {"name": "vee"}
    assert result["items"][0] == "aaaaa…[+15 chars]"
    assert sorted(result["items"][1]) == [1, 2]
    assert result["other"].startswith("<obje…")
    assert result["3"] is None
    json.dumps(result)


def test_disabled_mode_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "trace_log_enabled", False)
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    set_trace_writer(None)
    configure_trace_log("agent")
    trace_event("planner_plan", plan={"x": 1})
    assert not trace_enabled()
    assert list(tmp_path.iterdir()) == []


def test_configure_opens_service_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "trace_log_enabled", True)
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    try:
        configure_trace_log("agent")
        assert trace_enabled()
        trace_event("gate_decision", decision="reply")
        _close_installed()
        line = (tmp_path / "trace-agent.jsonl").read_text(encoding="utf-8")
        assert json.loads(line)["service"] == "agent"
    finally:
        set_trace_writer(None)


def test_configure_logs_when_the_dir_cannot_open(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(settings, "trace_log_enabled", True)
    monkeypatch.setattr(settings, "log_dir", str(blocker / "sub"))
    set_trace_writer(None)
    with caplog.at_level(logging.WARNING):
        configure_trace_log("agent")
    assert not trace_enabled()
    assert "trace_log_open_failed" in caplog.text


def test_record_head_has_turn_ids(trace_records: ReadTrace) -> None:
    request_token = request_id_var.set("-5441986530:174")
    chat_token = chat_id_var.set(CHAT_ID)
    try:
        trace_event("compose_result", reply="ок", service="ignored")
    finally:
        request_id_var.reset(request_token)
        chat_id_var.reset(chat_token)
    (record,) = trace_records()
    assert record["request_id"] == "-5441986530:174"
    assert record["chat_id"] == CHAT_ID
    assert record["service"] == "test"
    assert record["stage"] == "compose_result"
    assert record["reply"] == "ок"
    assert record["ts"].endswith("+00:00")


def test_record_clips_fields(trace_records: ReadTrace, monkeypatch) -> None:
    monkeypatch.setattr(settings, "trace_log_max_field_chars", 3)
    trace_event("retrieve", text="abcdef")
    assert trace_records()[0]["text"] == "abc…[+3 chars]"


def test_broken_record_logs_once(trace_records: ReadTrace, caplog) -> None:
    class _Broken:
        def __str__(self) -> str:
            raise RuntimeError("boom")

    with caplog.at_level(logging.WARNING):
        trace_event("x", value=_Broken())
        trace_event("x", value=_Broken())
    assert caplog.text.count("trace_log_record_failed") == 1
    assert trace_records() == []


def test_write_error_is_reported_once(tmp_path: Path, caplog) -> None:
    writer = TraceLogWriter(tmp_path / "t.jsonl", max_bytes=0, backup_count=1)
    writer.close()
    handler = writer._handler
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            try:
                raise OSError("disk full")
            except OSError:
                handler.handleError(logging.makeLogRecord({"msg": "x"}))
    assert caplog.text.count("trace_log_write_failed") == 1


def _close_installed() -> None:
    writer = trace_log._TraceState.writer
    assert writer is not None
    writer.close()
