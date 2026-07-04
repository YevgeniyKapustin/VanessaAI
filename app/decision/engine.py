from app.config.content import get_content
from app.core.messages import ContextMessage
from app.decision.context import DecisionContext, DecisionRule
from app.decision.models import DecisionResult
from app.decision.protocols import (
    IntentDetectorProtocol,
    NoiseFilterProtocol,
    RateLimiterProtocol,
    RelevanceCheckerProtocol,
    SessionWindowProtocol,
    TriggerCheckerProtocol,
)
from app.decision.rules import (
    ConsecutiveReplyRule,
    DirectAddressRule,
    IntentRule,
    NoiseRule,
    PlannerReplyRule,
    RateLimitRule,
    RelevanceRule,
    TriggerRule,
    _base,
)


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
        rules: list[DecisionRule] | None = None,
        block_consecutive_replies: bool | None = None,
    ) -> None:
        self._intent = intent_detector
        self._triggers = trigger_checker
        self._relevance = relevance_checker
        self._session = session_analyzer
        self._rate_limiter = rate_limiter
        block_consecutive = (
            block_consecutive_replies
            if block_consecutive_replies is not None
            else get_content().decision.block_consecutive_replies
        )
        self._rules = rules or [
            RateLimitRule(rate_limiter),
            NoiseRule(noise_filter),
            DirectAddressRule(),
            ConsecutiveReplyRule(
                intent_detector,
                trigger_checker,
                enabled=block_consecutive,
            ),
            PlannerReplyRule(),
            IntentRule(),
            TriggerRule(),
            RelevanceRule(relevance_threshold),
        ]

    def record_reply(self, telegram_chat_id: int) -> None:
        self._rate_limiter.record_reply(telegram_chat_id)

    async def decide(
        self,
        text: str,
        telegram_chat_id: int,
        recent_messages: list[ContextMessage],
        query_vector: list[float] | None = None,
        search_text: str | None = None,
        *,
        should_reply: bool | None = None,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
    ) -> DecisionResult:
        intent = self._intent.detect(text)
        trigger = self._triggers.detect(text)
        session_active = self._session.has_active_request(recent_messages)
        base_context = DecisionContext(
            text=text,
            telegram_chat_id=telegram_chat_id,
            recent_messages=recent_messages,
            query_vector=query_vector,
            intent=intent,
            trigger=trigger,
            session_active=session_active,
            relevance_score=0.0,
            should_reply=should_reply,
            mentions_bot=mentions_bot,
            reply_to_bot=reply_to_bot,
        )
        for rule in self._rules:
            if isinstance(rule, RelevanceRule):
                continue
            result = rule.evaluate(base_context)
            if result is not None:
                return result

        relevance_score = await self._relevance.score(
            text,
            query_vector=query_vector,
            search_text=search_text,
        )
        context = DecisionContext(
            text=text,
            telegram_chat_id=telegram_chat_id,
            recent_messages=recent_messages,
            query_vector=query_vector,
            intent=intent,
            trigger=trigger,
            session_active=session_active,
            relevance_score=relevance_score,
            should_reply=should_reply,
            mentions_bot=mentions_bot,
            reply_to_bot=reply_to_bot,
        )
        for rule in self._rules:
            if not isinstance(rule, RelevanceRule):
                continue
            result = rule.evaluate(context)
            if result is not None:
                return result
        return _base(context)
