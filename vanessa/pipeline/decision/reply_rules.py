from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.gate.addressing.continuation import (
    last_bot_reply_partner_sender_id,
)
from vanessa.pipeline.decision.gate.addressing.planner_gate import planner_affirms_reply
from vanessa.pipeline.decision.gate.expectation.reply_expectation import (
    expects_follow_up_after_bot,
    is_conversation_closure,
    is_third_party_about_bot,
    last_prior_role,
    listen_window_warrants_reply,
)
from vanessa.pipeline.decision.models import DecisionReason, DecisionResult
from vanessa.pipeline.decision.protocols import NoiseFilterProtocol
from vanessa.pipeline.decision.rule_outcomes import (
    _ignore,
    _reply,
)


def _listen_window_noise_skip(
    context: DecisionContext,
    noise: NoiseFilterProtocol,
) -> bool:
    if context.trigger.detected:
        return False
    return noise.is_definite_noise(context.text)


def _listen_window_skip(context: DecisionContext, noise: NoiseFilterProtocol) -> bool:
    if context.directly_addressed:
        return True
    if context.intent.mentions_bot:
        return True
    if _listen_window_noise_skip(context, noise):
        return True
    return is_conversation_closure(context.text)


def _listen_window_inapplicable(
    context: DecisionContext,
    noise: NoiseFilterProtocol,
) -> bool:
    if not context.in_listen_window:
        return True
    return _listen_window_skip(context, noise)


def _listen_window_partner_reply(context: DecisionContext) -> bool:
    if not context.sender_telegram_id:
        return False
    partner = last_bot_reply_partner_sender_id(context.recent_messages)
    return partner == context.sender_telegram_id


class ListenWindowRule:
    needs_relevance = False

    def __init__(self, noise_filter: NoiseFilterProtocol) -> None:
        self._noise = noise_filter

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if _listen_window_inapplicable(context, self._noise):
            return None
        if listen_window_warrants_reply(
            context.text,
            should_reply=context.should_reply,
            has_question=context.intent.has_question,
            trigger_detected=context.trigger.detected,
        ):
            return _reply(context, DecisionReason.LISTEN_WINDOW)
        if _listen_window_partner_reply(context):
            # The user the bot just answered keeps talking inside the window —
            # an explicit continuation even when the planner was neutral or
            # vetoed a reply ("ну чет ваще мало" right after the dossier).
            return _reply(context, DecisionReason.LISTEN_WINDOW)
        return None


class PlannerReplyRule:
    needs_relevance = False

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if context.in_listen_window:
            return None
        if context.should_reply is not False:
            return None
        if context.directly_addressed or context.intent.mentions_bot:
            return None
        return _ignore(context, DecisionReason.NOT_EXPECTED)


class PlannerYesRule:
    needs_relevance = False

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if context.should_reply is not True:
            return None
        return _reply(context, DecisionReason.PLANNER)


def _intent_third_party(context: DecisionContext) -> bool:
    if context.directly_addressed or context.intent.mentions_bot:
        return False
    return is_third_party_about_bot(context.text)


def _intent_affirmed(context: DecisionContext) -> bool:
    return context.addressed_with_expectation or planner_affirms_reply(context)


def _intent_reply(context: DecisionContext) -> DecisionResult | None:
    if _intent_affirmed(context):
        return _reply(context, DecisionReason.INTENT, intent_detected=True)
    if context.should_reply is False:
        return None
    if context.session_active:
        return _reply(context, DecisionReason.INTENT, intent_detected=True)
    return None


class IntentRule:
    needs_relevance = False

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not context.intent.detected:
            return None
        if _intent_third_party(context):
            return None
        return _intent_reply(context)


def _trigger_affirmed(context: DecisionContext) -> bool:
    if context.directly_addressed or context.intent.mentions_bot:
        return True
    if planner_affirms_reply(context):
        return True
    return context.session_active


def _trigger_reply(context: DecisionContext) -> DecisionResult | None:
    if _trigger_affirmed(context):
        return _reply(
            context,
            DecisionReason.FORCE_REPLY,
            trigger_detected=True,
        )
    if context.should_reply is False:
        return None
    if context.should_reply is None:
        return _reply(
            context,
            DecisionReason.FORCE_REPLY,
            trigger_detected=True,
        )
    return None


class TriggerRule:
    needs_relevance = False

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not context.trigger.detected:
            return None
        return _trigger_reply(context)


def _relevance_skip(context: DecisionContext, threshold: float) -> bool:
    return context.relevance_score < threshold or not context.session_active


def _relevance_forced_reply(context: DecisionContext) -> bool:
    return context.intent.detected or context.trigger.detected


def _relevance_follow_up(context: DecisionContext) -> DecisionResult:
    prior_role = last_prior_role(context.recent_messages)
    if expects_follow_up_after_bot(
        context.text,
        last_prior_role=prior_role,
    ):
        return _reply(context, DecisionReason.RELEVANT)
    return _ignore(context, DecisionReason.NO_REPLY_NEEDED)


class RelevanceRule:
    needs_relevance = True

    def __init__(self, threshold: float) -> None:
        self._threshold = threshold

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if _relevance_skip(context, self._threshold):
            return None
        if _relevance_forced_reply(context):
            return _reply(context, DecisionReason.RELEVANT)
        if is_conversation_closure(context.text):
            return _ignore(context, DecisionReason.NO_REPLY_NEEDED)
        return _relevance_follow_up(context)
