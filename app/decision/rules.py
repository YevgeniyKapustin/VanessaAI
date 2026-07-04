from app.core.messages import ContextMessage
from app.decision.context import DecisionContext
from app.decision.models import DecisionAction, DecisionReason, DecisionResult
from app.decision.planner_gate import planner_affirms_reply
from app.decision.reply_expectation import (
    expects_follow_up_after_bot,
    is_conversation_closure,
    is_dismissal_request,
    is_third_party_about_bot,
    is_unsolicited_remark,
    listen_window_warrants_reply,
)
from app.decision.protocols import (
    IntentDetectorProtocol,
    NoiseFilterProtocol,
    RateLimiterProtocol,
    TriggerCheckerProtocol,
)


class _PreRelevanceRuleMixin:
    @property
    def needs_relevance(self) -> bool:
        return False


class RateLimitRule(_PreRelevanceRuleMixin):
    def __init__(self, rate_limiter: RateLimiterProtocol) -> None:
        self._rate_limiter = rate_limiter

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not self._rate_limiter.is_limited(context.telegram_chat_id):
            return None
        return _ignore(context, DecisionReason.RATE_LIMITED)


class NoiseRule(_PreRelevanceRuleMixin):
    def __init__(self, noise_filter: NoiseFilterProtocol) -> None:
        self._noise = noise_filter

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if context.intent.detected or context.trigger.detected:
            return None
        if not self._noise.is_noise(context.text):
            return None
        return _ignore(context, DecisionReason.NOISE)


class DismissalRule(_PreRelevanceRuleMixin):
    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not is_dismissal_request(context.text):
            return None
        return _ignore(context, DecisionReason.DISMISSAL)


class ThirdPartyAboutBotRule(_PreRelevanceRuleMixin):
    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if context.directly_addressed or context.intent.mentions_bot:
            return None
        if not is_third_party_about_bot(context.text):
            return None
        return _ignore(context, DecisionReason.NOT_EXPECTED)


class DirectAddressRule(_PreRelevanceRuleMixin):
    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not context.directly_addressed:
            return None
        return _reply(context, DecisionReason.ADDRESSING)


class ConsecutiveReplyRule(_PreRelevanceRuleMixin):
    def __init__(
        self,
        intent_detector: IntentDetectorProtocol,
        trigger_checker: TriggerCheckerProtocol,
        *,
        enabled: bool,
    ) -> None:
        self._intent = intent_detector
        self._triggers = trigger_checker
        self._enabled = enabled

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not self._enabled or not context.recent_messages:
            return None
        last = context.recent_messages[-1]
        if last.role != "assistant":
            return None
        if context.directly_addressed:
            return None
        if context.in_listen_window:
            return None
        intent = self._intent.detect(context.text)
        trigger = self._triggers.detect(context.text)
        if intent.detected or trigger.detected:
            return None
        if context.should_reply is True:
            return None
        return _ignore(context, DecisionReason.CONSECUTIVE)


class ListenWindowRule(_PreRelevanceRuleMixin):
    def __init__(self, noise_filter: NoiseFilterProtocol) -> None:
        self._noise = noise_filter

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not context.in_listen_window:
            return None
        if context.directly_addressed or context.intent.mentions_bot:
            return None
        if self._noise.is_noise(context.text) and not context.trigger.detected:
            return None
        if is_conversation_closure(context.text):
            return None
        if not listen_window_warrants_reply(
            context.text,
            should_reply=context.should_reply,
            has_question=context.intent.has_question,
            trigger_detected=context.trigger.detected,
        ):
            return None
        return _reply(context, DecisionReason.LISTEN_WINDOW)


class PlannerReplyRule(_PreRelevanceRuleMixin):
    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if context.in_listen_window:
            return None
        if context.should_reply is not False:
            return None
        if context.directly_addressed or context.intent.mentions_bot:
            return None
        return _ignore(context, DecisionReason.NOT_EXPECTED)


class PlannerOverreachRule(_PreRelevanceRuleMixin):
    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if context.should_reply is not True:
            return None
        if planner_affirms_reply(context):
            return None
        if context.directly_addressed or context.in_listen_window:
            return None
        return _ignore(context, DecisionReason.NOT_EXPECTED)


class IntentRule(_PreRelevanceRuleMixin):
    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not context.intent.detected:
            return None
        if (
            not context.directly_addressed
            and not context.intent.mentions_bot
            and is_third_party_about_bot(context.text)
        ):
            return None
        if context.directly_addressed or context.intent.mentions_bot:
            return _reply(context, DecisionReason.INTENT, intent_detected=True)
        if planner_affirms_reply(context):
            return _reply(context, DecisionReason.INTENT, intent_detected=True)
        if context.should_reply is False:
            return None
        if context.session_active:
            return _reply(context, DecisionReason.INTENT, intent_detected=True)
        return None


class TriggerRule(_PreRelevanceRuleMixin):
    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not context.trigger.detected:
            return None
        if (
            context.directly_addressed
            or context.intent.mentions_bot
            or planner_affirms_reply(context)
            or context.session_active
        ):
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


class RelevanceRule:
    def __init__(self, threshold: float) -> None:
        self._threshold = threshold

    @property
    def needs_relevance(self) -> bool:
        return True

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if context.relevance_score < self._threshold or not context.session_active:
            return None
        if context.intent.detected or context.trigger.detected:
            return _reply(context, DecisionReason.RELEVANT)
        if is_conversation_closure(context.text):
            return _ignore(context, DecisionReason.NO_REPLY_NEEDED)
        prior_role = _last_prior_role(context.recent_messages)
        if expects_follow_up_after_bot(context.text, last_prior_role=prior_role):
            return _reply(context, DecisionReason.RELEVANT)
        return _ignore(context, DecisionReason.NO_REPLY_NEEDED)


def _last_prior_role(messages: list[ContextMessage]) -> str | None:
    if len(messages) < 2:
        return None
    return messages[-2].role


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
