"""SenderMetricsRule: gate rule that uses the sender's mood & relationship metrics.

Chronic high toxicity combined with low trust can suppress a reply — but only
for messages that are not a direct address, do not require a reply (trigger /
intent / listen window / planner) and are not from the owner. The guards mirror
the persona's hard rules: the owner is never affected by relational metrics.
"""

from __future__ import annotations

from vanessa.config.settings import settings
from vanessa.knowledge.metrics.schema import PersonMetrics
from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.models import (
    DecisionAction,
    DecisionReason,
    DecisionResult,
)


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


def is_low_attitude(
    *,
    annoyance: float,
    sender_metrics: PersonMetrics | None,
    annoyance_threshold: float,
    trust_threshold: float,
    sympathy_threshold: float,
) -> bool:
    """True when Vanessa's attitude to the sender is critically low.

    Two independent paths: the loop-repetition ``annoyance`` (runtime) or the
    persistently low relationship (``trust`` + ``sympathy`` from the person
    card). A zero-baseline card (trust=0, sympathy=0) never triggers — both
    persisted fields must be judged and both below their thresholds.
    """
    if annoyance >= annoyance_threshold:
        return True
    if sender_metrics is None:
        return False
    trust = sender_metrics.trust_score
    sympathy = sender_metrics.sympathy
    if trust is None or sympathy is None:
        return False
    return trust <= trust_threshold and sympathy <= sympathy_threshold


def _owner_exempt(context: DecisionContext) -> bool:
    owner = settings.required_user_telegram_id
    return bool(owner and context.sender_telegram_id == owner)


def _low_attitude_essential(context: DecisionContext) -> bool:
    if context.in_listen_window:
        return True
    if context.addressed_with_expectation:
        return True
    return context.should_reply is True


def _skip_low_attitude(context: DecisionContext) -> bool:
    if _owner_exempt(context):
        return True
    if not is_low_attitude(
        annoyance=context.annoyance,
        sender_metrics=context.sender_metrics,
        annoyance_threshold=settings.decision_annoyance_ignore_threshold,
        trust_threshold=settings.decision_low_attitude_trust_threshold,
        sympathy_threshold=settings.decision_low_attitude_sympathy_threshold,
    ):
        return True
    return _low_attitude_essential(context)


class LowAttitudeRule:
    """Maximal ignore tendency for a sender Vanessa's attitude to has collapsed.

    When her attitude is critically low (loop-repetition annoyance and/or a
    persistently low relationship), ANY weak / non-essential message is ignored
    — even one she merely dislikes a little. Essential cases (owner, a genuine
    direct address with expectation, an in-listen-window continuation, or an
    explicit planner reply) still get a reply, but coldly (the compose annoyance
    note turns the tone unkind).
    """

    needs_relevance = False

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not settings.decision_low_attitude_rule_enabled:
            return None
        if _skip_low_attitude(context):
            return None
        return DecisionResult(
            action=DecisionAction.IGNORE,
            reason=DecisionReason.LOW_ATTITUDE,
            relevance_score=context.relevance_score,
            intent_detected=context.intent.detected,
            trigger_detected=context.trigger.detected,
            session_active=context.session_active,
        )


def _metrics_address_guard(context: DecisionContext) -> bool:
    if context.directly_addressed:
        return True
    if context.addressed_with_expectation:
        return True
    return context.intent.mentions_bot


def _metrics_reply_guard(context: DecisionContext) -> bool:
    if context.trigger.detected:
        return True
    if context.in_listen_window:
        return True
    return context.should_reply is True


def _metrics_guarded(context: DecisionContext) -> bool:
    if _metrics_address_guard(context):
        return True
    return _metrics_reply_guard(context)


def _toxic_ignore_result(context: DecisionContext) -> DecisionResult | None:
    metrics = context.sender_metrics
    if metrics is None:
        return None
    if _metrics_guarded(context):
        return None
    if not should_ignore_for_toxicity(
        metrics,
        sender_telegram_id=context.sender_telegram_id,
        owner_telegram_id=settings.required_user_telegram_id,
    ):
        return None
    return DecisionResult(
        action=DecisionAction.IGNORE,
        reason=DecisionReason.TOXIC,
        relevance_score=context.relevance_score,
        intent_detected=context.intent.detected,
        trigger_detected=context.trigger.detected,
        session_active=context.session_active,
    )


class SenderMetricsRule:
    needs_relevance = False

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not settings.decision_metrics_rule_enabled:
            return None
        return _toxic_ignore_result(context)
