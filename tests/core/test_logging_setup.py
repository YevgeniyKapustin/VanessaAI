import json
import logging
import sys
from pathlib import Path

import app.core.logging_setup as logging_setup
from app.core.logging_setup import (
    JsonFormatter,
    LoguruStyleFormatter,
    RequestIdFilter,
    ServiceNameFilter,
    configure_logging,
    create_file_handler,
)
from app.core.request_context import request_id_var


def _make_record(**overrides: object) -> logging.LogRecord:
    base = {
        "name": "app.bot.handlers.messages",
        "level": logging.INFO,
        "pathname": __file__,
        "lineno": 42,
        "msg": "message_received chat_id=-100",
        "args": (),
        "exc_info": None,
        "func": "handle_text",
    }
    base.update(overrides)
    return logging.LogRecord(
        name=str(base["name"]),
        level=int(base["level"]),
        pathname=str(base["pathname"]),
        lineno=int(base["lineno"]),
        msg=str(base["msg"]),
        args=base["args"],
        exc_info=base["exc_info"],
        func=str(base["func"]),
    )


def test_configure_logging_adds_service_and_request_id():
    configure_logging("bot", level="DEBUG")

    token = request_id_var.set("test-123")
    try:
        record = _make_record()
        for log_filter in (
            RequestIdFilter(),
            ServiceNameFilter("bot"),
        ):
            assert log_filter.filter(record) is True
        assert record.request_id == "test-123"
        assert record.service == "bot"
    finally:
        request_id_var.reset(token)


def test_loguru_formatter_plain_output():
    formatter = LoguruStyleFormatter(colorize=False)
    record = _make_record()
    record.service = "bot"
    record.request_id = "-100:99"
    record.created = 1_700_000_000.0
    record.msecs = 123.0

    line = formatter.format(record)

    assert " | INFO     | bot:-100:99 | " in line
    assert "bot.handlers.messages:handle_text:42 | " in line
    assert line.endswith("message_received chat_id=-100")
    assert ".123" in line


def test_loguru_formatter_shortens_app_prefix():
    formatter = LoguruStyleFormatter(colorize=False)
    record = _make_record(name="app.services.conversation_orchestrator")
    record.service = "api"
    record.request_id = "-"
    record.funcName = "handle_incoming"

    line = formatter.format(record)

    assert "services.conversation_orchestrator:handle_incoming:42" in line
    assert "app.services" not in line


def test_loguru_formatter_includes_exception_traceback():
    formatter = LoguruStyleFormatter(colorize=False)
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="app.knowledge.writer",
            level=logging.ERROR,
            pathname=__file__,
            lineno=143,
            msg="knowledge_vector_reindex_failed path=%s",
            args=("People/x.md",),
            exc_info=sys.exc_info(),
            func="apply",
        )
    record.service = "api"
    record.request_id = "-"
    record.created = 1_700_000_000.0
    record.msecs = 123.0

    line = formatter.format(record)

    assert "knowledge_vector_reindex_failed path=People/x.md" in line
    assert "Traceback (most recent call last)" in line
    assert "ValueError: boom" in line


def test_create_file_handler_writes_plain_lines(tmp_path: Path) -> None:
    handler = create_file_handler(
        "api",
        "INFO",
        tmp_path,
        max_bytes=1024 * 1024,
        backup_count=1,
    )
    logger = logging.getLogger("app.test_file_logging")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        logger.info("hello file %s", 42)

        log_file = tmp_path / "api.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "hello file 42" in content
        assert "\033[" not in content  # no ANSI colors in files
    finally:
        handler.close()


def test_create_file_handler_rotates(tmp_path: Path) -> None:
    handler = create_file_handler(
        "bot",
        "INFO",
        tmp_path,
        max_bytes=256,
        backup_count=1,
    )
    logger = logging.getLogger("app.test_file_logging_rotate")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        for i in range(200):
            logger.info("padding line %d %s", i, "x" * 40)

        assert (tmp_path / "bot.log").exists()
        backups = sorted(tmp_path.glob("bot.log.*"))
        assert backups, "expected at least one rotated backup"
    finally:
        handler.close()


def test_json_formatter_emits_one_object() -> None:
    formatter = JsonFormatter()
    record = _make_record()
    record.service = "worker"
    record.request_id = "req-1"
    record.created = 1_700_000_000.0

    payload = json.loads(formatter.format(record))

    assert payload["service"] == "worker"
    assert payload["request_id"] == "req-1"
    assert payload["level"] == "INFO"
    assert payload["message"] == "message_received chat_id=-100"
    assert payload["logger"] == "app.bot.handlers.messages"
    assert payload["timestamp"].endswith("Z")


def test_json_formatter_includes_exception() -> None:
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="app.worker.main",
            level=logging.ERROR,
            pathname=__file__,
            lineno=10,
            msg="task_failed id=%s",
            args=("abc",),
            exc_info=sys.exc_info(),
            func="handle",
        )
    record.service = "worker"
    record.request_id = "-"

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "task_failed id=abc"
    assert "ValueError: boom" in payload["exception"]


def test_configure_logging_json_to_stdout(monkeypatch, capsys) -> None:
    logging_setup._configured_service = None
    logging.getLogger().handlers.clear()
    from app.config import settings

    monkeypatch.setattr(settings, "log_json", True)
    monkeypatch.setattr(settings, "log_file_enabled", False)
    try:
        configure_logging("bot", level="INFO")
        logging.getLogger("app.test_json").info("hello json %s", 7)
        line = capsys.readouterr().out.strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["message"] == "hello json 7"
        assert payload["service"] == "bot"
        assert payload["level"] == "INFO"
    finally:
        logging_setup._configured_service = None
        logging.getLogger().handlers.clear()
