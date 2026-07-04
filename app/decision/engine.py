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
from app.decision.gate.reply_eligibility import ReplyEligibility
from app.decision.gate.user_ignore import ChatIgnoreRegistry
from app.decision.rules import (
    ConsecutiveReplyRule,
    DirectAddressRule,
    HardIgnoreRule,
    IntentRule,
    ListenWindowRule,
    NoiseRule,
    PlannerOverreachRule,
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
        *,
        rules: list[DecisionRule] | None = None,
        block_consecutive_replies: bool = False,
        reply_eligibility: ReplyEligibility | None = None,
        ignore_registry: ChatIgnoreRegistry | None = None,
    ) -> None:
        self._intent = intent_detector
        self._triggers = trigger_checker
        self._relevance = relevance_checker
        self._session = session_analyzer
        self._rate_limiter = rate_limiter
        registry = ignore_registry or ChatIgnoreRegistry()
        eligibility = reply_eligibility or ReplyEligibility(
            intent_detector,
            trigger_checker,
            noise_filter,
            registry,
        )
        self._rules = rules or [
            RateLimitRule(rate_limiter),
            NoiseRule(noise_filter),
            HardIgnoreRule(eligibility),
            DirectAddressRule(),
            ConsecutiveReplyRule(
                intent_detector,
                trigger_checker,
                enabled=block_consecutive_replies,
            ),
            ListenWindowRule(noise_filter),
            PlannerReplyRule(),
            PlannerOverreachRule(),
            IntentRule(),
            TriggerRule(),
            RelevanceRule(relevance_threshold),
        ]
        self._pre_relevance_rules = [
            r for r in self._rules if not r.needs_relevance
        ]
        self._relevance_rules = [r for r in self._rules if r.needs_relevance]

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
        reply_to_other_user: bool = False,
        in_listen_window: bool = False,
        sender_telegram_id: int = 0,
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
            reply_to_other_user=reply_to_other_user,
            in_listen_window=in_listen_window,
            sender_telegram_id=sender_telegram_id,
        )
        for rule in self._pre_relevance_rules:
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
            reply_to_other_user=reply_to_other_user,
            in_listen_window=in_listen_window,
            sender_telegram_id=sender_telegram_id,
        )
        for rule in self._relevance_rules:
            result = rule.evaluate(context)
            if result is not None:
                return result
        return _base(context)
