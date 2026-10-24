"""Reader of the trace log: one turn in time order, or the recent turn list."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.trace_turn import main

TURN = "-5441986530:174"


def _write(path: Path, *records: dict) -> None:
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _record(ts: str, request_id: str, stage: str, **fields) -> dict:
    head = {"ts": ts, "service": "agent", "request_id": request_id}
    return {**head, "chat_id": -5441986530, "stage": stage, **fields}


def _logs(tmp_path: Path) -> Path:
    _write(
        tmp_path / "trace-agent.jsonl",
        _record("2026-10-24T10:00:02", TURN, "compose_reply", reply="я ещё ничего не скинула"),
        _record("2026-10-24T10:00:01", TURN, "planner", messages=[{"role": "user", "content": "привет"}]),
        _record("2026-10-24T09:00:00", "-1:1", "planner", output=""),
    )
    _write(
        tmp_path / "trace-worker.jsonl.1",
        _record("2026-10-24T10:00:03", TURN, "hermes_sent", parts=["отчёт"]),
    )
    return tmp_path


def test_prints_one_turn_in_time_order(tmp_path: Path, capsys) -> None:
    code = main([TURN, "--dir", str(_logs(tmp_path))])
    out = capsys.readouterr().out
    assert code == 0
    assert out.index("planner") < out.index("compose_reply") < out.index("hermes_sent")
    assert "--- user ---\nпривет" in out
    assert "[reply]\nя ещё ничего не скинула" in out
    assert '"отчёт"' in out
    assert "-1:1" not in out


def test_lists_recent_turns(tmp_path: Path, capsys) -> None:
    assert main(["--dir", str(_logs(tmp_path)), "--last", "1"]) == 0
    assert capsys.readouterr().out.strip().endswith(TURN)


def test_reads_one_file(tmp_path: Path, capsys) -> None:
    _logs(tmp_path)
    file = str(tmp_path / "trace-worker.jsonl.1")
    assert main(["--file", file, TURN]) == 0
    out = capsys.readouterr().out
    assert "hermes_sent" in out
    assert "compose_reply" not in out


def test_unknown_turn_returns_one(tmp_path: Path, capsys) -> None:
    assert main(["-9:9", "--dir", str(_logs(tmp_path))]) == 1
    assert "no records" in capsys.readouterr().out
