from dataclasses import replace

from vanessa.pipeline.decision.context import DecisionContext, DecisionRule
from vanessa.pipeline.decision.engine_gate import (
    apply_compose_gate,
    resolve_eligibility_gate,
)
from vanessa.pipeline.decision.engine_rules import (
    default_decision_rules,
    first_matching_result,
)
from vanessa.pipeline.decision.gate.addressing.compose_gate import ComposeGatePolicy
from vanessa.pipeline.decision.gate.eligibility.user_ignore import ChatIgnoreRegistry
from vanessa.pipeline.decision.gate.protocols import ReplyEligibilityProtocol
from vanessa.pipeline.decision.models import DecisionResult
from vanessa.pipeline.decision.protocols import (
    IntentDetectorProtocol,
    NoiseFilterProtocol,
    RateLimiterProtocol,
    RelevanceCheckerProtocol,
    SessionWindowProtocol,
    TriggerCheckerProtocol,
)
from vanessa.pipeline.decision.rule_outcomes import _base


class DecisionEngine:
    def __init__(
        self,
        intent_detector: IntentDetectorProtocol,
        trigger_checker: TriggerCheckerProtocol,
        relevance_checker: RelevanceCheckerProtocol,
        session_analyzer: SessionWindowProtocol,
        rate_limiter: RateLimiterProtocol,
        noise_filter: NoiseFilterProtocol,
        relevance_threshold: float,
        *,
        rules: list[DecisionRule] | None = None,
        block_consecutive_replies: bool = False,
        reply_eligibility: ReplyEligibilityProtocol | None = None,
        ignore_registry: ChatIgnoreRegistry | None = None,
        compose_gate: ComposeGatePolicy | None = None,
    ) -> None:
        self._intent = intent_detector
        self._triggers = trigger_checker
        self._relevance = relevance_checker
        self._session = session_analyzer
        self._rate_limiter = rate_limiter
        eligibility, self._compose_gate = resolve_eligibility_gate(
            intent_detector,
            trigger_checker,
            noise_filter,
            reply_eligibility=reply_eligibility,
            ignore_registry=ignore_registry,
            compose_gate=compose_gate,
        )
        self._rules = rules or default_decision_rules(
            intent_detector,
            trigger_checker,
            rate_limiter,
            noise_filter,
            eligibility,
            relevance_threshold=relevance_threshold,
            block_consecutive_replies=block_consecutive_replies,
        )
        self._pre_relevance_rules = [
            r for r in self._rules if not r.needs_relevance
        ]
        self._relevance_rules = [r for r in self._rules if r.needs_relevance]

    def record_reply(self, chat_id: int | str) -> None:
        self._rate_limiter.record_reply(chat_id)

    async def decide(
        self,
        context: DecisionContext,
        *,
        search_text: str | None = None,
        humor_ok: bool = False,
    ) -> DecisionResult:
        context = replace(
            context,
            intent=self._intent.detect(context.text),
            trigger=self._triggers.detect(context.text),
            session_active=self._session.has_active_request(
                context.recent_messages,
            ),
        )
        result = first_matching_result(self._pre_relevance_rules, context)
        if result is not None:
            return apply_compose_gate(
                self._compose_gate,
                result,
                context,
                humor_ok=humor_ok,
            )

        relevance_score = await self._relevance.score(
            context.text,
            query_vector=context.query_vector,
            search_text=search_text,
        )
        context = replace(context, relevance_score=relevance_score)
        result = first_matching_result(self._relevance_rules, context)
        if result is None:
            result = _base(context)
        return apply_compose_gate(
            self._compose_gate,
            result,
            context,
            humor_ok=humor_ok,
        )
