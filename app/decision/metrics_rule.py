"""SenderMetricsRule: gate rule that uses the sender's mood & relationship metrics.

Chronic high toxicity combined with low trust can suppress a reply — but only
for messages that are not a direct address, do not require a reply (trigger /
intent / listen window / planner) and are not from the owner. The guards mirror
the persona's hard rules: the owner is never affected by relational metrics.
"""

from __future__ import annotations

from app.config.settings import settings
from app.decision.context import DecisionContext
from app.decision.models import DecisionAction, DecisionReason, DecisionResult
from app.knowledge.metrics.schema import PersonMetrics


def should_ignore_for_toxicity(
    metrics: PersonMetrics,
    *,
    sender_telegram_id: int,
    owner_telegram_id: int,
) -> bool:
    """True when the sender's persistent profile warrants ignoring the message.

    Requires a recent-ish snapshot with both toxicity and trust judged. The
    owner is always exempt.
    """
    if owner_telegram_id and sender_telegram_id == owner_telegram_id:
        return False
    if metrics.toxicity is None or metrics.trust_score is None:
        return False
    return (
        metrics.toxicity >= settings.decision_toxicity_ignore_threshold
        and metrics.trust_score <= settings.decision_trust_ignore_threshold
    )


class SenderMetricsRule:
    @property
    def needs_relevance(self) -> bool:
        return False

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not settings.decision_metrics_rule_enabled:
            return None
        metrics = context.sender_metrics
        if metrics is None:
            return None
        # Guards: never suppress direct/expected replies, triggers, or the owner.
        if context.directly_addressed or context.addressed_with_expectation:
            return None
        if context.intent.mentions_bot:
            return None
        if context.trigger.detected:
            return None
        if context.in_listen_window:
            return None
        if context.should_reply is True:
            return None
        if should_ignore_for_toxicity(
            metrics,
            sender_telegram_id=context.sender_telegram_id,
            owner_telegram_id=settings.required_user_telegram_id,
        ):
            return DecisionResult(
                action=DecisionAction.IGNORE,
                reason=DecisionReason.TOXIC,
                relevance_score=context.relevance_score,
                intent_detected=context.intent.detected,
                trigger_detected=context.trigger.detected,
                session_active=context.session_active,
            )
        return None
