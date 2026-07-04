import pytest

from app.decision.context import DecisionContext
from app.decision.detectors.intent import IntentResult
from app.decision.models import DecisionAction, DecisionReason
from app.decision.gate.planner_gate import planner_affirms_reply
from app.decision.rules import PlannerOverreachRule
from app.decision.detectors.triggers import TriggerResult


def _ctx(**kwargs) -> DecisionContext:
    defaults = dict(
        text="test",
        telegram_chat_id=1,
        recent_messages=[],
        query_vector=None,
        intent=IntentResult(detected=False),
        trigger=TriggerResult(detected=False),
        session_active=False,
        relevance_score=0.0,
        should_reply=None,
        mentions_bot=False,
        reply_to_bot=False,
        in_listen_window=False,
    )
    defaults.update(kwargs)
    return DecisionContext(**defaults)


def test_planner_affirms_requires_address_or_listen_window():
    assert planner_affirms_reply(_ctx(should_reply=True)) is False
    assert planner_affirms_reply(
        _ctx(should_reply=True, mentions_bot=True, intent=IntentResult(True, mentions_bot=True))
    ) is True
    assert planner_affirms_reply(
        _ctx(should_reply=True, in_listen_window=True)
    ) is True


def test_planner_overreach_rule_ignores_loose_planner_true():
    rule = PlannerOverreachRule()
    result = rule.evaluate(
        _ctx(
            should_reply=True,
            intent=IntentResult(detected=True, has_question=True),
        )
    )
    assert result is not None
    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.NOT_EXPECTED
