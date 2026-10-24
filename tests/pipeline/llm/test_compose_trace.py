"""Compose trace records: prompt, every API output, the final reply."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

from tests.trace_helpers import ReadTrace
from vanessa.pipeline.llm.planner.generation_config import LLMGenerationParams
from vanessa.pipeline.llm.providers.compose_trace import (
    trace_claude_output,
    trace_openai_output,
)
from vanessa.pipeline.llm.providers.deepseek import DeepSeekLLMProvider

# Untagged leaked reasoning: compose retries it with ``strict=True``.
LEAK = "Он просто зовёт по имени. Отвечаю сухо"


def _response(text: str, reasoning: str = "") -> MagicMock:
    choice = MagicMock(finish_reason="stop")
    choice.message = MagicMock(content=text, reasoning_content=reasoning)
    return MagicMock(choices=[choice])


def _provider(*responses: MagicMock) -> DeepSeekLLMProvider:
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(side_effect=list(responses))
    return DeepSeekLLMProvider(
        client=client,
        model="test-model",
        max_retries=1,
        generation=LLMGenerationParams(temperature=0.8, top_p=0.9, max_tokens=64),
    )


async def test_generate_writes_prompt_outputs_and_reply(
    trace_records: ReadTrace,
) -> None:
    provider = _provider(
        _response(LEAK),
        _response("думаю\n[answer]\nчего", reasoning="план"),
    )
    assert await provider.generate("ванесса", []) == "Чего"
    stages = [record["stage"] for record in trace_records()]
    assert stages == [
        "compose_prompt",
        "compose_output",
        "compose_output",
        "compose_reply",
    ]
    prompt, first, retry, reply = trace_records()
    assert prompt["model"] == "test-model"
    assert prompt["system"]
    assert "ванесса" in prompt["user"]
    assert (first["strict"], retry["strict"]) == (False, True)
    assert first["output"] == LEAK
    assert retry["reasoning_content"] == "план"
    assert retry["finish_reason"] == "stop"
    assert reply["reply"] == "Чего"
    assert reply["reasoning"] == "думаю"


def test_claude_output_record(trace_records: ReadTrace) -> None:
    response = MagicMock(stop_reason="end_turn")
    response.content = [MagicMock(text="[answer]\nок")]
    trace_claude_output("claude-x", response, strict=False)
    (record,) = trace_records()
    assert record["output"] == "[answer]\nок"
    assert record["finish_reason"] == "end_turn"


def test_broken_response_is_logged_not_raised(
    trace_records: ReadTrace, caplog
) -> None:
    with caplog.at_level(logging.WARNING):
        trace_openai_output("m", object(), strict=False)
        trace_claude_output("m", object(), strict=True)
    assert trace_records() == []
    assert caplog.text.count("trace_log_record_failed") == 1


def test_helpers_are_silent_when_disabled() -> None:
    trace_openai_output("m", object(), strict=False)
    trace_claude_output("m", object(), strict=False)
