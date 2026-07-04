from __future__ import annotations

from app.decision.context import DecisionContext
from app.decision.gate.protocols import ReplyEligibilityProtocol
from app.decision.gate.reply_expectation import (
    expects_follow_up_after_bot,
    last_prior_role,
)
from app.decision.models import DecisionAction, DecisionReason, DecisionResult


_PRE_APPROVED_REASONS = frozenset(
    {
        DecisionReason.ADDRESSING,
        DecisionReason.FORCE_REPLY,
        DecisionReason.LISTEN_WINDOW,
    }
)


class ComposeGatePolicy:
    def __init__(self, eligibility: ReplyEligibilityProtocol) -> None:
        self._eligibility = eligibility

    def should_downgrade_to_ignore(
        self,
        result: DecisionResult,
        context: DecisionContext,
        *,
        humor_ok: bool,
    ) -> bool:
        if result.action != DecisionAction.REPLY:
            return False
        if result.reason in _PRE_APPROVED_REASONS:
            return False
        if result.reason == DecisionReason.RELEVANT and expects_follow_up_after_bot(
            context.text,
            last_prior_role=last_prior_role(context.recent_messages),
        ):
            return False
        return self._eligibility.should_block_compose(
            context.text,
            mentions_bot=context.mentions_bot,
            reply_to_bot=context.reply_to_bot,
            reply_to_other_user=context.reply_to_other_user,
            should_reply=context.should_reply,
            in_listen_window=context.in_listen_window,
            humor_ok=humor_ok,
            trigger_detected=context.trigger.detected,
            intent=context.intent,
        )
