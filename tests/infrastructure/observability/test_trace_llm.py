"""Trace hook at the chat-completer boundary."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.trace_helpers import ReadTrace
from vanessa.config.settings import settings
from vanessa.core.request_context import request_id_var
from vanessa.infrastructure.observability.trace_log.llm import trace_llm_call
from vanessa.llm.completers import DeepSeekChatCompleter

MESSAGES = [{"role": "user", "content": "hello"}]


def _in_turn():
    return request_id_var.set("-100:7")


def test_full_record_inside_a_turn(trace_records: ReadTrace, monkeypatch) -> None:
    monkeypatch.setattr(settings, "trace_log_max_reasoning_chars", 4)
    token = _in_turn()
    try:
        trace_llm_call(
            provider="deepseek",
            model="m",
            kind="turn_plan",
            messages=MESSAGES,
            output='{"should_reply": true}',
            reasoning="long reasoning",
            usage={"total_tokens": 9},
        )
    finally:
        request_id_var.reset(token)
    (record,) = trace_records()
    assert record["stage"] == "turn_plan"
    assert record["messages"] == MESSAGES
    assert record["output"] == '{"should_reply": true}'
    assert record["reasoning_content"] == "long…[+10 chars]"
    assert record["usage"] == {"total_tokens": 9}
    assert "compact" not in record


def test_compact_record_without_a_turn(trace_records: ReadTrace) -> None:
    trace_llm_call(
        provider="deepseek",
        model="m",
        kind="portrait",
        messages=MESSAGES,
        output="x" * 700,
    )
    (record,) = trace_records()
    assert record["request_id"] == "-"
    assert record["compact"] is True
    assert record["prompt_chars"] == len("hello")
    assert "messages" not in record
    assert record["output"].endswith("…[+100 chars]")


def test_hook_is_silent_when_disabled() -> None:
    trace_llm_call(provider="p", model="m", kind="k", messages=MESSAGES)


def test_hook_survives_bad_messages(trace_records: ReadTrace) -> None:
    trace_llm_call(provider="p", model="m", kind="k", messages=[None])  # type: ignore[list-item]
    assert trace_records() == []


def _response(text: str) -> MagicMock:
    message = MagicMock(content=text, reasoning_content="why")
    usage = MagicMock(prompt_tokens=3, completion_tokens=2, total_tokens=5)
    usage.prompt_cache_hit_tokens = 0
    usage.prompt_cache_miss_tokens = 3
    return MagicMock(choices=[MagicMock(message=message)], usage=usage)


async def test_completer_writes_success_record(trace_records: ReadTrace) -> None:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_response("ok"))
    token = _in_turn()
    try:
        text = await DeepSeekChatCompleter(client).complete(
            "m", MESSAGES, kind="reaction_gate"
        )
    finally:
        request_id_var.reset(token)
    assert text == "ok"
    (record,) = trace_records()
    assert record["stage"] == "reaction_gate"
    assert record["request_id"] == "-100:7"
    assert record["output"] == "ok"
    assert record["reasoning_content"] == "why"
    assert record["error"] is None


async def test_completer_writes_error_record(trace_records: ReadTrace) -> None:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=TimeoutError())
    with pytest.raises(TimeoutError):
        await DeepSeekChatCompleter(client).complete("m", MESSAGES, kind="memory")
    (record,) = trace_records()
    assert record["stage"] == "memory"
    assert record["error"] == "TimeoutError"
