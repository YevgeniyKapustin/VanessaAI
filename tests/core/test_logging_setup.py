import logging

from app.core.logging_setup import (
    LoguruStyleFormatter,
    RequestIdFilter,
    ServiceNameFilter,
    configure_logging,
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
