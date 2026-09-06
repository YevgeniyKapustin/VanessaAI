from vanessa.pipeline.decision.context import DecisionContext, DecisionRule
from vanessa.pipeline.decision.gate.protocols import ReplyEligibilityProtocol
from vanessa.pipeline.decision.metrics_rule import LowAttitudeRule, SenderMetricsRule
from vanessa.pipeline.decision.models import DecisionResult
from vanessa.pipeline.decision.protocols import (
    IntentDetectorProtocol,
    NoiseFilterProtocol,
    RateLimiterProtocol,
    TriggerCheckerProtocol,
)
from vanessa.pipeline.decision.repeated_question import RepeatedQuestionRule
from vanessa.pipeline.decision.rules import (
    ConsecutiveReplyRule,
    DirectAddressRule,
    HardIgnoreRule,
    IntentRule,
    ListenWindowRule,
    NoiseRule,
    PlannerReplyRule,
    PlannerYesRule,
    RateLimitRule,
    RelevanceRule,
    TriggerRule,
)


def default_decision_rules(
    intent_detector: IntentDetectorProtocol,
    trigger_checker: TriggerCheckerProtocol,
    rate_limiter: RateLimiterProtocol,
    noise_filter: NoiseFilterProtocol,
    eligibility: ReplyEligibilityProtocol,
    *,
    relevance_threshold: float,
    block_consecutive_replies: bool,
) -> list[DecisionRule]:
    return [
        RateLimitRule(rate_limiter),
        NoiseRule(noise_filter),
        HardIgnoreRule(eligibility),
        RepeatedQuestionRule(),
        LowAttitudeRule(),
        DirectAddressRule(),
        ConsecutiveReplyRule(
            intent_detector,
            trigger_checker,
            enabled=block_consecutive_replies,
        ),
        ListenWindowRule(noise_filter),
        PlannerReplyRule(),
        PlannerYesRule(),
        IntentRule(),
        TriggerRule(),
        SenderMetricsRule(),
        RelevanceRule(relevance_threshold),
    ]


def first_matching_result(
    rules: list[DecisionRule],
    context: DecisionContext,
) -> DecisionResult | None:
    for rule in rules:
        result = rule.evaluate(context)
        if result is not None:
            return result
    return None
