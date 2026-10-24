"""Compose guard: a reply never promises a later result with no lookup."""

import logging

import pytest

from vanessa.core.generate_request import GenerateRequest
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.stages import ComposeStage
from vanessa.pipeline.stages.compose_promise import (
    is_false_promise,
    without_false_promise,
)

_PROMISE = "Ща гляну, что ты там наворотил за день — скину списком"
_HONEST = "Сейчас не могу это проверить, спроси позже"


class ScriptedLLM:
    def __init__(self, *replies: str | Exception) -> None:
        self._replies = list(replies)
        self.requests: list[GenerateRequest] = []

    async def generate(self, request: GenerateRequest, *args, **kwargs) -> str:
        _ = args, kwargs
        self.requests.append(request)
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _request(status: str | None) -> GenerateRequest:
    return GenerateRequest(
        user_message="что я делал сегодня", context_blocks=[], hermes_status=status
    )


@pytest.mark.parametrize("status", [None, "offline"])
def test_promise_without_lookup_is_false(status: str | None) -> None:
    assert is_false_promise(_request(status), _PROMISE) is True


def test_promise_with_lookup_is_fine() -> None:
    assert is_false_promise(_request("asked"), _PROMISE) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [None, "offline"])
async def test_false_promise_regenerated(status, caplog) -> None:
    llm = ScriptedLLM(_HONEST)
    with caplog.at_level(logging.WARNING, logger="vanessa.pipeline.stages"):
        reply = await without_false_promise(llm, _request(status), _PROMISE)
    assert reply == _HONEST
    assert llm.requests[0].false_promise_retry is True
    assert "compose_false_promise" in caplog.text


@pytest.mark.asyncio
async def test_asked_turn_keeps_promise() -> None:
    llm = ScriptedLLM()
    reply = await without_false_promise(llm, _request("asked"), _PROMISE)
    assert reply == _PROMISE
    assert llm.requests == []


@pytest.mark.asyncio
async def test_failed_retry_keeps_first_reply() -> None:
    llm = ScriptedLLM(RuntimeError("down"))
    reply = await without_false_promise(llm, _request(None), _PROMISE)
    assert reply == _PROMISE


@pytest.mark.asyncio
async def test_second_promise_is_logged(caplog) -> None:
    llm = ScriptedLLM("Погоди, найду — скину")
    with caplog.at_level(logging.WARNING, logger="vanessa.pipeline.stages"):
        reply = await without_false_promise(llm, _request(None), _PROMISE)
    assert reply == "Погоди, найду — скину"
    assert "compose_false_promise_kept" in caplog.text


@pytest.mark.asyncio
async def test_compose_stage_replaces_false_promise() -> None:
    message = "ванесса что я делал сегодня"
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-1001, message=message, sender_telegram_id=42
        )
    )
    ctx.turn_plan = TurnPlan(original=message, text=message, skip_search=True)
    llm = ScriptedLLM(_PROMISE, _HONEST)
    assert await ComposeStage(llm).run(ctx) is True
    assert ctx.reply == _HONEST
    assert [r.false_promise_retry for r in llm.requests] == [False, True]
