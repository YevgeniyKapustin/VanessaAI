from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.models import (
    DecisionAction,
    DecisionReason,
    DecisionResult,
)


def _base(context: DecisionContext) -> DecisionResult:
    return DecisionResult(
        action=DecisionAction.IGNORE,
        reason=DecisionReason.IGNORE,
        relevance_score=context.relevance_score,
        intent_detected=context.intent.detected,
        trigger_detected=context.trigger.detected,
        session_active=context.session_active,
    )


def _ignore(context: DecisionContext, reason: DecisionReason) -> DecisionResult:
    result = _base(context)
    return DecisionResult(
        action=result.action,
        reason=reason,
        relevance_score=result.relevance_score,
        intent_detected=result.intent_detected,
        trigger_detected=result.trigger_detected,
        session_active=result.session_active,
    )


def _reply(
    context: DecisionContext,
    reason: DecisionReason,
    *,
    intent_detected: bool | None = None,
    trigger_detected: bool | None = None,
) -> DecisionResult:
    return DecisionResult(
        action=DecisionAction.REPLY,
        reason=reason,
        relevance_score=context.relevance_score,
        intent_detected=(
            context.intent.detected
            if intent_detected is None
            else intent_detected
        ),
        trigger_detected=(
            context.trigger.detected
            if trigger_detected is None
            else trigger_detected
        ),
        session_active=context.session_active,
    )
