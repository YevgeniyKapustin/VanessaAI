from vanessa.core.session.channel_keys import dialogue_session_key
from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.gate.protocols import ReplyEligibilityProtocol
from vanessa.pipeline.decision.models import DecisionReason, DecisionResult
from vanessa.pipeline.decision.protocols import (
    IntentDetectorProtocol,
    NoiseFilterProtocol,
    RateLimiterProtocol,
    TriggerCheckerProtocol,
)
from vanessa.pipeline.decision.reply_rules import (
    IntentRule,
    ListenWindowRule,
    PlannerReplyRule,
    PlannerYesRule,
    TriggerRule,
)
from vanessa.pipeline.decision.rule_outcomes import (
    _base,
    _ignore,
    _reply,
)

__all__ = [
    "ConsecutiveReplyRule",
    "DirectAddressRule",
    "HardIgnoreRule",
    "IntentRule",
    "ListenWindowRule",
    "NoiseRule",
    "PlannerReplyRule",
    "PlannerYesRule",
    "RateLimitRule",
    "TriggerRule",
    "_base",
    "_ignore",
    "_reply",
]


class RateLimitRule:
    def __init__(self, rate_limiter: RateLimiterProtocol) -> None:
        self._rate_limiter = rate_limiter

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        key = dialogue_session_key(
            channel=context.channel,
            telegram_chat_id=context.telegram_chat_id,
        )
        if not self._rate_limiter.is_limited(key):
            return None
        return _ignore(context, DecisionReason.RATE_LIMITED)


class NoiseRule:
    def __init__(self, noise_filter: NoiseFilterProtocol) -> None:
        self._noise = noise_filter

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if context.intent.detected or context.trigger.detected:
            return None
        # Only unambiguous filler/acknowledgment is hard-dropped here.
        # Short-but-possibly-meaningful messages are not — they already survived
        # the LLM planner and the deterministic gate, so the neural network's
        # verdict decides.
        if not self._noise.is_definite_noise(context.text):
            return None
        return _ignore(context, DecisionReason.NOISE)


class HardIgnoreRule:
    def __init__(self, eligibility: ReplyEligibilityProtocol) -> None:
        self._eligibility = eligibility

    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        hard = self._eligibility.hard_ignore(context)
        if hard is None:
            return None
        return _ignore(context, hard.decision_reason)


class DirectAddressRule:
    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not context.telegram_addressed_with_expectation:
            return None
        return _reply(context, DecisionReason.ADDRESSING)


class ConsecutiveReplyRule:
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
        intent = self._intent.detect(context.text)
        trigger = self._triggers.detect(context.text)
        if (
            context.directly_addressed
            or context.in_listen_window
            or intent.detected
            or trigger.detected
            or context.should_reply is True
        ):
            return None
        return _ignore(context, DecisionReason.CONSECUTIVE)
