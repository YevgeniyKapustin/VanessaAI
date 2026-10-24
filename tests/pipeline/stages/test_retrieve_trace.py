"""Retrieve and planner trace records hold the text compose will see."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock

from tests.trace_helpers import ReadTrace
from vanessa.core.messages import ContextMessage
from vanessa.core.turn import ChatTurnInput
from vanessa.knowledge.schema import KnowledgeBlock
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.llm.planner.turn_planner import TurnPlanner
from vanessa.pipeline.stages.retrieve_trace import trace_retrieve

BLOCK = KnowledgeBlock(path="People/team.md", title="Команда", kind="note", content="Боб")
AT = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def _ctx() -> TurnPipelineContext:
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(telegram_chat_id=-100, message="что с MR?", sender_telegram_id=42)
    )
    ctx.turn_plan = TurnPlan(
        original="что с MR?", text="", skip_search=True,
        ask_hermes=True, hermes_query=" статус MR ",
    )
    ctx.hermes_status = "asked"
    ctx.knowledge_blocks = [BLOCK]
    ctx.recent = [
        ContextMessage(id=1, role="assistant", content="отчёт готов", created_at=AT),
        ContextMessage(id=2, role="user", content="что с MR?", sender_name="Женя"),
    ]
    ctx.session = MagicMock(earlier_messages=[ContextMessage(id=0, role="user", content="давно")])
    return ctx


def test_retrieve_record_has_hermes_knowledge_and_session(
    trace_records: ReadTrace,
) -> None:
    trace_retrieve(_ctx())
    (record,) = trace_records()
    assert record["stage"] == "retrieve"
    assert record["hermes_status"] == "asked"
    assert record["hermes_query"] == "статус MR"
    assert record["knowledge"] == [{"path": "People/team.md", "title": "Команда", "text": "Боб"}]
    (line,) = record["session"]
    assert line["text"] == "отчёт готов"
    assert line["at"] == AT.isoformat()
    assert record["earlier"][0]["text"] == "давно"


def test_retrieve_trace_never_raises(trace_records: ReadTrace, caplog) -> None:
    ctx = _ctx()
    ctx.recent = [None, None]  # type: ignore[list-item]
    with caplog.at_level(logging.WARNING):
        trace_retrieve(ctx)
    assert trace_records() == []
    assert "trace_log_record_failed" in caplog.text


def test_retrieve_trace_is_silent_when_disabled() -> None:
    trace_retrieve(_ctx())


class _Completer:
    async def complete(self, model, messages, *, kind="completion", **kwargs):
        del model, messages, kind, kwargs
        return '{"should_reply": true, "ask_hermes": true, "hermes_query": "MR?"}'


async def test_planner_writes_parsed_plan(trace_records: ReadTrace) -> None:
    planner = TurnPlanner(use_llm=True, llm_client=_Completer())
    plan = await planner._plan_with_llm("ванесса, что с MR?", [])
    (record,) = trace_records()
    assert record["stage"] == "planner_plan"
    assert record["plan"]["ask_hermes"] is plan.ask_hermes is True
    assert record["plan"]["hermes_query"] == "MR?"
