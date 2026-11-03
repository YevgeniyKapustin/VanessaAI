"""Decision rules for proxy questions and the owner's DM."""

from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.models import DecisionAction, DecisionReason
from vanessa.pipeline.decision.proxy_rules import OwnerDmRule, ProxyQuestionRule


def _context(**overrides) -> DecisionContext:
    values = {"text": "Евгений, когда релиз?"}
    values.update(overrides)
    return DecisionContext(**values)


def test_proxy_question_is_replied() -> None:
    result = ProxyQuestionRule().evaluate(_context(proxy_question=True))

    assert result is not None
    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.PROXY_QUESTION


def test_proxy_rule_ignores_normal_turn() -> None:
    assert ProxyQuestionRule().evaluate(_context()) is None


def test_owner_dm_is_replied() -> None:
    result = OwnerDmRule().evaluate(
        _context(owner_dm=True, sender_is_owner=True, is_private_chat=True)
    )

    assert result is not None
    assert result.reason == DecisionReason.OWNER_DM


def test_owner_dm_rule_needs_the_owner() -> None:
    assert OwnerDmRule().evaluate(_context(owner_dm=True)) is None
