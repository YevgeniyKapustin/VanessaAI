"""Compose stage: untagged model output never ends as a "repeated" silence."""

import logging

import pytest

from vanessa.config.content import get_content
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.models import DecisionReason
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.llm.tagged_reply import UntaggedReplyError
from vanessa.pipeline.stages import ComposeStage


class UntaggedLLM:
    async def generate(self, *args, **kwargs):
        _ = args, kwargs
        raise UntaggedReplyError("test-model")


def _ctx(message: str, **turn) -> TurnPipelineContext:
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-1001,
            message=message,
            sender_telegram_id=42,
            **turn,
        )
    )
    ctx.turn_plan = TurnPlan(original=message, text=message, skip_search=True)
    return ctx


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "turn"),
    [
        ("ванесса расскажи о себе", {}),
        ("расскажи о себе", {"mentions_bot": True}),
        ("расскажи о себе", {"reply_to_bot": True}),
    ],
)
async def test_direct_request_gets_safe_line(message, turn, caplog):
    ctx = _ctx(message, **turn)
    with caplog.at_level(logging.WARNING, logger="vanessa.pipeline.stages"):
        assert await ComposeStage(UntaggedLLM()).run(ctx) is True
    assert ctx.reply == get_content().llm.untagged_fallback.strip()
    assert ctx.refuse_reason is None
    assert "compose_untagged_fallback" in caplog.text


@pytest.mark.asyncio
async def test_side_message_stays_silent_with_own_reason(caplog):
    ctx = _ctx("расскажи о себе")
    with caplog.at_level(logging.INFO, logger="vanessa.pipeline.stages"):
        assert await ComposeStage(UntaggedLLM()).run(ctx) is False
    assert ctx.reply is None
    assert ctx.refuse_reason == DecisionReason.UNTAGGED.value
    assert "compose_refuse_untagged" in caplog.text
    assert "compose_refuse_empty" not in caplog.text
