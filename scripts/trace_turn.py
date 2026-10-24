"""Print the trace records of one turn in time order (stdlib only).

    python scripts/trace_turn.py -5441986530:174 [--dir logs] [--file path]
    python scripts/trace_turn.py --last 20      # recent turns, newest last

Reads ``<dir>/trace-*.jsonl*`` (all services and rotated backups) unless
``--file`` is given. ``--dir`` defaults to ``$LOG_DIR`` or ``logs``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

HEAD_KEYS = ("ts", "service", "request_id", "chat_id", "stage")
# Chat ids are negative: «-5441986530:174» would read as an option.
_NEGATIVE_ID = re.compile(r"^-\d+:")


def _files(args: argparse.Namespace) -> list[Path]:
    if args.file:
        return [Path(item) for item in args.file]
    return sorted(Path(args.dir).glob("trace-*.jsonl*"))


def _records(paths: list[Path]) -> Iterator[dict]:
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def _value(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def _messages(messages: list[dict]) -> str:
    return "\n".join(
        f"--- {item.get('role')} ---\n{_value(item.get('content'))}" for item in messages
    )


def render(record: dict) -> str:
    head = " ".join(str(record.get(key)) for key in HEAD_KEYS)
    lines = [f"=== {head}"]
    for key, value in record.items():
        if key in HEAD_KEYS or value in (None, "", [], {}):
            continue
        text = _messages(value) if key == "messages" else _value(value)
        lines.append(f"[{key}]\n{text}")
    return "\n".join(lines)


def list_turns(records: list[dict], last: int) -> str:
    turns: dict[str, dict] = {}
    for record in records:
        turns.setdefault(record.get("request_id"), record)
    rows = [f"{r['ts']} {r.get('chat_id')} {rid}" for rid, r in turns.items()]
    return "\n".join(rows[-last:])


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show one turn from the trace log.")
    parser.add_argument("request_id", nargs="?")
    parser.add_argument("--dir", default=os.environ.get("LOG_DIR") or "logs")
    parser.add_argument("--file", action="append")
    parser.add_argument("--last", type=int, default=20)
    ids = [item for item in argv if _NEGATIVE_ID.match(item)]
    rest = [item for item in argv if not _NEGATIVE_ID.match(item)]
    return parser.parse_args([*rest, "--", *ids] if ids else rest)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    records = sorted(_records(_files(args)), key=lambda item: item.get("ts", ""))
    if not args.request_id:
        print(list_turns(records, args.last))
        return 0
    found = [item for item in records if item.get("request_id") == args.request_id]
    print("\n\n".join(render(item) for item in found) or "no records")
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
